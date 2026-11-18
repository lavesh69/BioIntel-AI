from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any

try:
    import streamlit as st
except ImportError:
    st = None

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
LICENSE_CATALOG_DIR = ROOT / "data" / "step170" / "license_catalog"
USER_LICENSE_DIR = ROOT / "UserData" / "config" / "engine_licenses"
VERIFICATION_REQUIRED = "License Verification Requires Vendor Confirmation"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact_secret(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return "Not supplied"
    if len(clean) <= 8:
        return "••••••••"
    return f"{clean[:4]}…{clean[-4:]}"


def load_registered_licenses() -> list[dict[str, Any]]:
    """Load policy metadata and user evidence without inventing rights or keys."""
    records: list[dict[str, Any]] = []
    for file in sorted(LICENSE_CATALOG_DIR.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping invalid license policy %s: %s", file, exc)
            continue
        records.append({
            "id": str(data.get("licence_id") or file.stem),
            "engine_name": str(data.get("label") or file.stem.replace("-", " ").title()),
            "license_type": str(data.get("licence_id") or "Not declared"),
            "redistribution_status": str(data.get("redistribution_status") or "Unknown — review required"),
            "commercial_use_status": "Not established by this catalogue",
            "user_supplied_license_status": "Not supplied",
            "expiry": "Not provided",
            "source": str(data.get("terms_url") or file.as_posix()),
            "verification_method": str(data.get("acceptance_mode") or "Policy review"),
            "configuration_path": "Not configured",
            "status": VERIFICATION_REQUIRED,
            "secret": "Not supplied",
            "audit_record": str(data.get("notes") or "Policy metadata loaded; rights not independently verified."),
        })
    if USER_LICENSE_DIR.is_dir():
        for file in sorted(USER_LICENSE_DIR.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Skipping invalid user license record %s: %s", file, exc)
                continue
            records.append({
                "id": str(data.get("id") or file.stem),
                "engine_name": str(data.get("engine_name") or "Unnamed engine"),
                "license_type": str(data.get("license_type") or "Not declared"),
                "redistribution_status": str(data.get("redistribution_status") or "Unknown — review required"),
                "commercial_use_status": str(data.get("commercial_use_status") or "Unknown — review required"),
                "user_supplied_license_status": "Evidence recorded — not independently verified",
                "expiry": str(data.get("expiry") or "Not provided"),
                "source": str(data.get("source") or "User-supplied evidence"),
                "verification_method": str(data.get("verification_method") or "Vendor confirmation required"),
                "configuration_path": str(data.get("configuration_path") or "Not configured"),
                "status": VERIFICATION_REQUIRED,
                "secret": "Redacted / not stored",
                "audit_record": str(data.get("audit_record") or data.get("recorded_at") or "Recorded locally"),
            })
    return records


def verify_license_key(key: str, *, vendor_verifier: Any | None = None) -> dict[str, Any]:
    """Fail closed unless an explicitly configured vendor verifier validates the key."""
    clean = str(key or "").strip()
    result = {
        "valid": False,
        "key": redact_secret(clean),
        "signature": "Not verified",
        "verified_at": _utc_now(),
        "verification_status": VERIFICATION_REQUIRED,
        "message": VERIFICATION_REQUIRED,
    }
    if not clean:
        result["message"] = "No license credential was supplied."
        return result
    if vendor_verifier is None:
        return result
    try:
        evidence = vendor_verifier(clean)
    except Exception as exc:
        logger.warning("Vendor license verification failed safely: %s", type(exc).__name__)
        result["message"] = "Vendor verification could not be completed."
        return result
    if isinstance(evidence, dict) and evidence.get("valid") is True and evidence.get("vendor_reference"):
        result.update({
            "valid": True,
            "signature": str(evidence["vendor_reference"]),
            "verification_status": "Vendor Verified",
            "message": "License verified by the configured vendor adapter.",
        })
    return result


def record_license_evidence(
    *,
    engine_name: str,
    license_type: str,
    source: str,
    configuration_path: str = "",
    expiry: str = "",
    redistribution_status: str = "Unknown — review required",
    commercial_use_status: str = "Unknown — review required",
) -> Path:
    """Record non-secret evidence; this never upgrades status to verified."""
    name = " ".join(engine_name.strip().split())
    if not name:
        raise ValueError("Engine name is required.")
    if source and not source.lower().startswith(("https://", "file:")):
        raise ValueError("Evidence source must be an HTTPS URL or a file reference.")
    USER_LICENSE_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")[:80] or "engine"
    path = USER_LICENSE_DIR / f"{slug}.json"
    payload = {
        "schema": "biointel.engine-license-evidence.v1",
        "id": f"user-{slug}",
        "engine_name": name,
        "license_type": license_type.strip() or "Not declared",
        "source": source.strip() or "User-supplied evidence",
        "configuration_path": configuration_path.strip() or "Not configured",
        "expiry": expiry.strip() or "Not provided",
        "redistribution_status": redistribution_status,
        "commercial_use_status": commercial_use_status,
        "verification_method": "Vendor confirmation required",
        "status": VERIFICATION_REQUIRED,
        "recorded_at": _utc_now(),
        "audit_record": "Evidence recorded locally. No secret or license key was stored.",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def render_engine_license_manager() -> None:
    if st is None:
        return
    st.title("BioIntel Legal & Component Notices")
    st.caption(
        "This restricted legal workspace preserves required upstream component identities, licence terms, source references and redistribution evidence. Normal BioIntel product screens use BioIntel public names only."
    )
    licenses = load_registered_licenses()
    verified = sum(record["status"] == "Vendor Verified" for record in licenses)
    columns = st.columns(4)
    columns[0].metric("Policy and evidence records", len(licenses))
    columns[1].metric("Vendor verified", verified)
    columns[2].metric("Confirmation required", len(licenses) - verified)
    columns[3].metric("Secrets displayed", "0")
    st.warning(
        "Catalogue metadata is not proof of redistribution or commercial rights. "
        "Third-party vendor confirmation remains required unless a real verifier provides evidence."
    )

    with st.expander("Record non-secret license evidence", on_change="rerun"):
        with st.form("record_license_evidence"):
            engine_name = st.text_input("Upstream component name")
            license_type = st.text_input("License type")
            source = st.text_input("Terms or evidence source", placeholder="https://vendor.example/terms")
            configuration_path = st.text_input("Configuration path (no secret values)")
            expiry = st.text_input("Expiry, if documented")
            submitted = st.form_submit_button("Record evidence", type="primary")
        if submitted:
            try:
                path = record_license_evidence(
                    engine_name=engine_name,
                    license_type=license_type,
                    source=source,
                    configuration_path=configuration_path,
                    expiry=expiry,
                )
                st.success(f"Evidence recorded without storing a key: {path.name}")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    st.subheader("Required upstream component and data-licence catalogue")
    display_fields = [
        "engine_name", "license_type", "redistribution_status", "commercial_use_status",
        "user_supplied_license_status", "expiry", "source", "verification_method",
        "configuration_path", "status", "audit_record",
    ]
    st.dataframe(
        [{key: record.get(key) for key in display_fields} for record in licenses],
        hide_index=True,
        column_config={"source": st.column_config.LinkColumn("Source")},
    )
