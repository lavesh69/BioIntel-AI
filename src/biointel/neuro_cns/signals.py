from __future__ import annotations

import io
import math
import tempfile
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import signal
from scipy.stats import kurtosis
from sklearn.decomposition import FastICA
from sklearn.exceptions import ConvergenceWarning

from biointel.neuro_cns.schemas import table_quality_report


BANDS: dict[str, tuple[float, float]] = {
    "delta": (0.5, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 80.0),
}


def optional_signal_adapter_status() -> dict[str, bool]:
    try:
        import mne  # noqa: F401
        return {"mne": True, "edf": True, "bdf": True, "fif": True}
    except Exception:
        return {"mne": False, "edf": False, "bdf": False, "fif": False}


def load_signal_payload(data: bytes, filename: str, *, maximum_samples: int = 2_000_000, maximum_channels: int = 256) -> dict[str, Any]:
    """Load core tabular signals and optional EDF/BDF/FIF recordings with strict size guards."""
    name = str(filename or "").lower()
    metadata: dict[str, Any] = {"filename": filename, "format": None, "adapter_status": optional_signal_adapter_status()}
    if name.endswith((".csv", ".tsv", ".txt")):
        separator = "\t" if name.endswith((".tsv", ".txt")) else ","
        frame = pd.read_csv(io.BytesIO(data), sep=separator)
        metadata["format"] = "tabular"
        return {"frame": frame, "sampling_rate_hz": None, "metadata": metadata}
    if name.endswith((".edf", ".bdf", ".fif", ".fif.gz")):
        try:
            import mne
        except Exception as exc:
            raise ValueError("EDF/BDF/FIF upload requires the optional MNE adapter to be installed and qualified.") from exc
        suffix = ".fif.gz" if name.endswith(".fif.gz") else Path(name).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
            handle.write(data)
            handle.flush()
            if name.endswith(".edf"):
                raw = mne.io.read_raw_edf(handle.name, preload=False, verbose="ERROR")
            elif name.endswith(".bdf"):
                raw = mne.io.read_raw_bdf(handle.name, preload=False, verbose="ERROR")
            else:
                raw = mne.io.read_raw_fif(handle.name, preload=False, verbose="ERROR")
            if len(raw.ch_names) > maximum_channels:
                raise ValueError(f"Recording has {len(raw.ch_names)} channels; maximum supported in one interactive run is {maximum_channels}.")
            sample_count = int(raw.n_times)
            if sample_count > maximum_samples:
                stop = maximum_samples
                truncated = True
            else:
                stop = sample_count
                truncated = False
            values = raw.get_data(start=0, stop=stop)
            frame = pd.DataFrame(values.T, columns=[str(channel) for channel in raw.ch_names])
            metadata.update({
                "format": "MNE recording",
                "channel_count": len(raw.ch_names),
                "original_samples": sample_count,
                "loaded_samples": len(frame),
                "truncated": truncated,
                "measurement_date": str(raw.info.get("meas_date") or ""),
            })
            return {"frame": frame, "sampling_rate_hz": float(raw.info["sfreq"]), "metadata": metadata}
    raise ValueError("Supported signal formats are CSV/TSV/TXT. EDF/BDF/FIF require the optional qualified MNE adapter.")


def _filter_channel(values: np.ndarray, rate: float, low_hz: float, high_hz: float, line_noise_hz: float | None) -> np.ndarray:
    cleaned = signal.detrend(values, type="linear")
    nyquist = rate / 2.0
    low = max(0.01, float(low_hz))
    high = min(float(high_hz), nyquist * 0.95)
    if low >= high:
        raise ValueError("Band-pass low frequency must be below high frequency and the Nyquist limit.")
    sos = signal.butter(4, [low / nyquist, high / nyquist], btype="bandpass", output="sos")
    cleaned = signal.sosfiltfilt(sos, cleaned)
    if line_noise_hz and 0 < line_noise_hz < nyquist:
        b, a = signal.iirnotch(float(line_noise_hz), Q=30.0, fs=rate)
        cleaned = signal.filtfilt(b, a, cleaned)
    return cleaned


def _spectral_entropy(density: np.ndarray) -> float:
    values = np.maximum(np.asarray(density, dtype=float), 0.0)
    if values.sum() <= 0:
        return 0.0
    probabilities = values / values.sum()
    entropy = -np.sum(probabilities * np.log2(probabilities + 1e-15))
    return float(entropy / max(np.log2(len(values)), 1e-12))


def analyze_neural_signals(
    frame: pd.DataFrame,
    sampling_rate_hz: float,
    time_column: str | None = None,
    *,
    low_cut_hz: float = 0.5,
    high_cut_hz: float = 80.0,
    line_noise_hz: float | None = None,
    compute_connectivity: bool = True,
) -> dict[str, Any]:
    rate = float(sampling_rate_hz)
    if not math.isfinite(rate) or rate <= 1:
        raise ValueError("Sampling rate must be a finite value greater than 1 Hz.")
    data = frame.copy()
    if time_column and time_column in data.columns:
        observed_time = pd.to_numeric(data[time_column], errors="coerce")
        if observed_time.notna().sum() >= 3:
            intervals = np.diff(observed_time.dropna().to_numpy(float))
            estimated_rate = 1.0 / np.median(intervals[intervals > 0]) if np.any(intervals > 0) else rate
        else:
            estimated_rate = rate
        data = data.drop(columns=[time_column])
    else:
        estimated_rate = rate
    numeric = data.select_dtypes(include=[np.number]).copy()
    if numeric.empty:
        numeric = data.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    if numeric.empty:
        raise ValueError("No numeric signal channels were found.")
    original_missing = numeric.isna().mean()
    numeric = numeric.interpolate(limit_direction="both").fillna(0.0)
    if len(numeric) < max(64, int(rate * 2)):
        raise ValueError("Signal is too short for stable filtered spectral analysis.")

    channel_rows: list[dict[str, Any]] = []
    psd_frames: list[pd.DataFrame] = []
    event_rows: list[dict[str, Any]] = []
    filtered_channels: dict[str, np.ndarray] = {}
    for channel in numeric.columns:
        values = numeric[channel].to_numpy(float)
        centered = _filter_channel(values, rate, low_cut_hz, high_cut_hz, line_noise_hz)
        filtered_channels[str(channel)] = centered
        nperseg = min(len(centered), max(128, int(rate * 4)))
        frequencies, density = signal.welch(centered, fs=rate, nperseg=nperseg)
        total_mask = (frequencies >= max(0.5, low_cut_hz)) & (frequencies <= min(high_cut_hz, rate / 2))
        total_power = float(np.trapezoid(density[total_mask], frequencies[total_mask])) if total_mask.any() else 0.0
        valid_density = density[total_mask] if total_mask.any() else density
        valid_frequencies = frequencies[total_mask] if total_mask.any() else frequencies
        dominant_frequency = float(valid_frequencies[int(np.argmax(valid_density))]) if len(valid_density) else 0.0
        robust_scale = float(np.median(np.abs(values - np.median(values))))
        high_amplitude_fraction = float(np.mean(np.abs(values - np.median(values)) > 8 * max(robust_scale, 1e-9)))
        flatline_fraction = float(np.mean(np.abs(np.diff(values)) < 1e-12))
        row: dict[str, Any] = {
            "channel": str(channel),
            "samples": len(values),
            "mean": round(float(values.mean()), 6),
            "std": round(float(values.std(ddof=0)), 6),
            "peak_to_peak": round(float(np.ptp(values)), 6),
            "missing_fraction_input": round(float(original_missing.get(channel, 0.0)), 6),
            "flatline_fraction": round(flatline_fraction, 6),
            "extreme_sample_fraction": round(high_amplitude_fraction, 6),
            "total_band_power": round(total_power, 8),
            "dominant_frequency_hz": round(dominant_frequency, 4),
            "spectral_entropy": round(_spectral_entropy(valid_density), 6),
        }
        for band, (low, high) in BANDS.items():
            mask = (frequencies >= max(low, low_cut_hz)) & (frequencies < min(high, high_cut_hz, rate / 2))
            power = float(np.trapezoid(density[mask], frequencies[mask])) if mask.any() else 0.0
            row[f"{band}_power"] = round(power, 8)
            row[f"{band}_relative"] = round(power / total_power, 6) if total_power > 0 else 0.0
        robust_center = float(np.median(centered))
        robust_mad = float(np.median(np.abs(centered - robust_center)))
        event_threshold = robust_center + 10.0 * max(robust_mad, 1e-12)
        candidate_indices, _ = signal.find_peaks(np.abs(centered - robust_center), height=abs(event_threshold - robust_center), distance=max(1, int(rate * 0.20)))
        for sample_index in candidate_indices[:500]:
            event_rows.append({"channel": str(channel), "sample_index": int(sample_index), "time_seconds": round(float(sample_index / rate), 6), "absolute_amplitude": round(float(abs(centered[sample_index] - robust_center)), 6), "event_kind": "high-amplitude candidate"})
        row["candidate_event_count"] = int(len(candidate_indices))
        row["artifact_flags"] = ", ".join(
            flag
            for flag, active in (
                ("flatline", flatline_fraction > 0.20),
                ("extreme_amplitude", high_amplitude_fraction > 0.01),
                ("near_zero_variance", row["std"] < 1e-9),
                ("high_missingness", row["missing_fraction_input"] > 0.10),
            )
            if active
        ) or "none"
        channel_rows.append(row)
        psd_frames.append(pd.DataFrame({"frequency_hz": frequencies, "power_spectral_density": density, "channel": str(channel)}))
    summary = pd.DataFrame(channel_rows)

    correlation = pd.DataFrame()
    coherence_rows: list[dict[str, Any]] = []
    if compute_connectivity and len(filtered_channels) >= 2:
        filtered_frame = pd.DataFrame(filtered_channels)
        correlation = filtered_frame.corr()
        names = list(filtered_channels)
        for left_index, left in enumerate(names):
            for right in names[left_index + 1 :]:
                frequencies, coherence = signal.coherence(filtered_channels[left], filtered_channels[right], fs=rate, nperseg=min(len(numeric), max(128, int(rate * 2))))
                for band, (low, high) in BANDS.items():
                    mask = (frequencies >= low) & (frequencies < min(high, rate / 2))
                    value = float(np.nanmean(coherence[mask])) if mask.any() else np.nan
                    coherence_rows.append({"channel_a": left, "channel_b": right, "band": band, "mean_coherence": round(value, 6) if np.isfinite(value) else None})

    quality = table_quality_report(frame)
    artifact_channels = int((summary["artifact_flags"] != "none").sum()) if not summary.empty else 0
    quality_grade = "good" if artifact_channels == 0 and quality.missing_fraction < 0.01 else "review" if artifact_channels <= max(1, len(summary) // 4) else "poor"
    return {
        "channel_summary": summary,
        "power_spectral_density": pd.concat(psd_frames, ignore_index=True),
        "channel_correlation": correlation,
        "band_coherence": pd.DataFrame(coherence_rows),
        "candidate_events": pd.DataFrame(event_rows),
        "sampling_rate_hz": rate,
        "sampling_rate_estimated_from_time": round(float(estimated_rate), 6),
        "duration_seconds": round(len(numeric) / rate, 6),
        "channel_count": len(numeric.columns),
        "signal_quality_grade": quality_grade,
        "artifact_channel_count": artifact_channels,
        "preprocessing": {"bandpass_hz": [low_cut_hz, min(high_cut_hz, rate / 2)], "line_noise_notch_hz": line_noise_hz, "detrend": "linear", "missing_values": "interpolated"},
        "input_fingerprint_sha256": quality.fingerprint_sha256,
        "optional_adapter_status": optional_signal_adapter_status(),
        "scientific_boundary": "Exploratory signal analytics with filtering and connectivity summaries; not a medical-device diagnostic.",
    }


def _numeric_signal_frame(frame: pd.DataFrame, time_column: str | None = None, event_column: str | None = None) -> pd.DataFrame:
    working = frame.drop(columns=[column for column in (time_column, event_column) if column and column in frame.columns], errors="ignore")
    numeric = working.select_dtypes(include=[np.number]).copy()
    if numeric.empty:
        numeric = working.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    if numeric.empty:
        raise ValueError("No numeric signal channels were found.")
    return numeric.interpolate(limit_direction="both").fillna(0.0)


def neural_signal_workflow(
    frame: pd.DataFrame,
    sampling_rate_hz: float,
    time_column: str | None = None,
    *,
    event_column: str | None = None,
    reference_mode: str = "average",
    bad_channel_policy: str = "flag_only",
    low_cut_hz: float = 0.5,
    high_cut_hz: float = 80.0,
    line_noise_hz: float | None = None,
    epoch_before_seconds: float = 0.2,
    epoch_after_seconds: float = 0.8,
    run_ica_review: bool = False,
    maximum_preview_points: int = 5000,
    random_state: int = 42,
) -> dict[str, Any]:
    """Preprocess, quality-review and summarize EEG/MEG research signals."""
    rate = float(sampling_rate_hz)
    if rate <= 1 or not math.isfinite(rate):
        raise ValueError("Sampling rate must be greater than 1 Hz.")
    numeric = _numeric_signal_frame(frame, time_column, event_column)
    reference = str(reference_mode or "none").strip().lower()
    if reference not in {"none", "average", "median"}:
        raise ValueError("Reference mode must be none, average or median.")
    referenced = numeric.copy()
    if reference == "average":
        referenced = referenced.sub(referenced.mean(axis=1), axis=0)
    elif reference == "median":
        referenced = referenced.sub(referenced.median(axis=1), axis=0)

    analysis = analyze_neural_signals(
        referenced,
        rate,
        None,
        low_cut_hz=low_cut_hz,
        high_cut_hz=high_cut_hz,
        line_noise_hz=line_noise_hz,
        compute_connectivity=True,
    )
    summary = analysis["channel_summary"]
    bad_channels = summary.loc[summary["artifact_flags"] != "none", "channel"].astype(str).tolist() if not summary.empty else []
    corrected = referenced.copy()
    policy = str(bad_channel_policy or "flag_only").strip().lower()
    if policy not in {"flag_only", "interpolate", "exclude"}:
        raise ValueError("Bad-channel policy must be flag_only, interpolate or exclude.")
    if bad_channels and policy == "interpolate":
        good = [column for column in corrected.columns if str(column) not in bad_channels]
        if good:
            replacement = corrected[good].mean(axis=1)
            for channel in bad_channels:
                if channel in corrected.columns:
                    corrected[channel] = replacement
    elif bad_channels and policy == "exclude":
        corrected = corrected.drop(columns=[channel for channel in bad_channels if channel in corrected.columns])
        if corrected.shape[1] < 1:
            raise ValueError("All channels were flagged; exclusion would leave no analyzable signal.")
    if policy != "flag_only" and bad_channels:
        analysis = analyze_neural_signals(
            corrected,
            rate,
            None,
            low_cut_hz=low_cut_hz,
            high_cut_hz=high_cut_hz,
            line_noise_hz=line_noise_hz,
            compute_connectivity=True,
        )

    preview_step = max(1, int(math.ceil(len(corrected) / max(1, maximum_preview_points))))
    preview = corrected.iloc[::preview_step].copy()
    preview.insert(0, "time_seconds", np.arange(0, len(corrected), preview_step)[: len(preview)] / rate)

    spectrogram_rows: list[dict[str, Any]] = []
    for channel in list(corrected.columns)[:8]:
        values = _filter_channel(corrected[channel].to_numpy(float), rate, low_cut_hz, high_cut_hz, line_noise_hz)
        nperseg = min(len(values), max(64, int(rate * 2)))
        frequencies, times, power = signal.spectrogram(values, fs=rate, nperseg=nperseg, noverlap=nperseg // 2, scaling="density")
        frequency_mask = (frequencies >= low_cut_hz) & (frequencies <= min(high_cut_hz, rate / 2))
        selected_freq = frequencies[frequency_mask]
        selected_power = power[frequency_mask]
        time_stride = max(1, int(math.ceil(len(times) / 120)))
        freq_stride = max(1, int(math.ceil(len(selected_freq) / 80)))
        for fi in range(0, len(selected_freq), freq_stride):
            for ti in range(0, len(times), time_stride):
                spectrogram_rows.append({
                    "channel": str(channel),
                    "time_seconds": round(float(times[ti]), 6),
                    "frequency_hz": round(float(selected_freq[fi]), 6),
                    "power": float(selected_power[fi, ti]),
                })

    evoked = pd.DataFrame()
    event_summary = pd.DataFrame()
    if event_column and event_column in frame.columns:
        event_values = frame[event_column]
        numeric_events = pd.to_numeric(event_values, errors="coerce")
        if numeric_events.notna().any():
            event_indices = np.flatnonzero(numeric_events.fillna(0).to_numpy() != 0)
        else:
            event_indices = np.flatnonzero(event_values.fillna("").astype(str).str.strip().ne("").to_numpy())
        before = max(0, int(round(epoch_before_seconds * rate)))
        after = max(1, int(round(epoch_after_seconds * rate)))
        epochs: list[np.ndarray] = []
        accepted_events: list[int] = []
        matrix = corrected.to_numpy(float)
        for index in event_indices:
            start, stop = int(index - before), int(index + after + 1)
            if start >= 0 and stop <= len(matrix):
                epoch = matrix[start:stop].copy()
                baseline_stop = min(before, len(epoch))
                if baseline_stop > 0:
                    epoch -= epoch[:baseline_stop].mean(axis=0, keepdims=True)
                epochs.append(epoch)
                accepted_events.append(int(index))
        if epochs:
            stacked = np.stack(epochs, axis=0)
            mean_epoch = stacked.mean(axis=0)
            time_axis = (np.arange(mean_epoch.shape[0]) - before) / rate
            evoked = pd.DataFrame(mean_epoch, columns=[str(column) for column in corrected.columns])
            evoked.insert(0, "relative_time_seconds", time_axis)
        event_summary = pd.DataFrame([{
            "event_column": event_column,
            "detected_events": int(len(event_indices)),
            "accepted_epochs": int(len(accepted_events)),
            "rejected_edge_epochs": int(len(event_indices) - len(accepted_events)),
            "epoch_window_seconds": f"-{epoch_before_seconds:g} to +{epoch_after_seconds:g}",
        }])

    ica_components = pd.DataFrame()
    ica_converged: bool | None = None
    if run_ica_review and corrected.shape[1] >= 2 and len(corrected) >= 200:
        component_count = min(corrected.shape[1], 20)
        sample_step = max(1, int(math.ceil(len(corrected) / 20000)))
        sample = corrected.iloc[::sample_step].to_numpy(float)
        sample = sample - sample.mean(axis=0, keepdims=True)
        try:
            ica = FastICA(n_components=component_count, whiten="unit-variance", random_state=random_state, max_iter=1200, tol=0.002)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ConvergenceWarning)
                sources = ica.fit_transform(sample)
            ica_converged = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
            component_kurtosis = kurtosis(sources, axis=0, fisher=True, bias=False, nan_policy="omit")
            eog_channels = [index for index, name in enumerate(corrected.columns) if any(token in str(name).lower() for token in ("eog", "veog", "heog"))]
            rows = []
            for index in range(component_count):
                max_eog_correlation = None
                if eog_channels:
                    correlations = [abs(float(np.corrcoef(sources[:, index], sample[:, channel_index])[0, 1])) for channel_index in eog_channels]
                    max_eog_correlation = max(correlations) if correlations else None
                rows.append({
                    "component": index + 1,
                    "kurtosis": round(float(component_kurtosis[index]), 6),
                    "max_eog_correlation": round(float(max_eog_correlation), 6) if max_eog_correlation is not None and math.isfinite(max_eog_correlation) else None,
                    "review_flag": bool(abs(float(component_kurtosis[index])) >= 8 or (max_eog_correlation is not None and max_eog_correlation >= 0.45)),
                })
            ica_components = pd.DataFrame(rows)
        except Exception as exc:
            ica_components = pd.DataFrame([{"component": None, "review_flag": True, "error": f"ICA review unavailable: {type(exc).__name__}: {exc}"}])

    analysis.update({
        "referenced_signal_preview": preview,
        "spectrogram": pd.DataFrame(spectrogram_rows),
        "evoked_response": evoked,
        "event_summary": event_summary,
        "ica_component_review": ica_components,
        "bad_channels_initial": bad_channels,
        "bad_channel_policy": policy,
        "reference_mode": reference,
        "preview_downsample_factor": preview_step,
        "ica_converged": ica_converged,
        "workflow_warnings": [
            warning for warning, active in (
                ("Bad channels were flagged but not altered.", bool(bad_channels and policy == "flag_only")),
                ("ICA components are review candidates only; no component was removed automatically.", bool(run_ica_review)),
                ("ICA did not fully converge; component rows remain review-only and should not be used for automatic rejection.", bool(run_ica_review and ica_converged is False)),
                ("No valid event epochs were available.", bool(event_column and event_summary.empty)),
            ) if active
        ],
        "scientific_boundary": "Exploratory preprocessing, spectral, connectivity, ERP and ICA-review workflow; no automated seizure, sleep-stage or clinical diagnosis is produced.",
    })
    return analysis
