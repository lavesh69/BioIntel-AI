from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)
_NCT_PATTERN = re.compile(r"^NCT\d{8}$")


@dataclass(frozen=True)
class ClinicalTrialRecord:
    nct_id: str
    title: str
    status: str
    conditions: tuple[str, ...]
    interventions: tuple[str, ...]
    phase: str
    sponsor: str
    url: str


class ClinicalTrialsService:
    """Fail-closed ClinicalTrials.gov API v2 client with bounded cache fallback."""

    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        *,
        opener: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] | None = None,
        now: Callable[[], float] | None = None,
        timeout: float = 6.0,
        retries: int = 2,
    ) -> None:
        root = Path(workspace_root or Path.cwd()).resolve()
        self.cache_dir = root / "UserData" / "cache" / "clinical_trials"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleeper or time.sleep
        self._now = now or time.time
        self.timeout, self.retries = max(1.0, timeout), max(0, retries)
        self.last_status = "Not Requested"
        self.last_error = ""
        self.last_http_status: int | None = None
        self.last_retrieved_at: str | None = None
        self.last_source = "ClinicalTrials.gov API v2"
        self.next_page_token: str | None = None

    @staticmethod
    def _validate_query(query: str) -> str:
        clean = " ".join(str(query).strip().split())
        if not clean:
            raise ValueError("Enter a condition, intervention, sponsor, or NCT ID.")
        if len(clean) > 300:
            raise ValueError("Search term must be 300 characters or fewer.")
        if any(ord(char) < 32 for char in clean):
            raise ValueError("Search term contains unsupported control characters.")
        return clean

    def _cache_path(self, query: str) -> Path:
        digest = hashlib.sha256(query.casefold().encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"trials_{digest}.json"

    def _request(self, url: str) -> dict[str, Any]:
        error = "ClinicalTrials.gov is unavailable."
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "BioIntel-Platform/15.6.0"},
            )
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    self.last_http_status = int(getattr(response, "status", 200))
                    if self.last_http_status == 429:
                        raise RuntimeError("Rate Limited")
                    if not 200 <= self.last_http_status < 300:
                        raise RuntimeError(f"HTTP {self.last_http_status}")
                    payload = json.loads(response.read().decode("utf-8"))
                    if not isinstance(payload, dict) or not isinstance(payload.get("studies", []), list):
                        raise RuntimeError("Invalid provider response")
                    return payload
            except urllib.error.HTTPError as exc:
                self.last_http_status = exc.code
                error = "Rate Limited" if exc.code == 429 else f"HTTP {exc.code}"
                if exc.code in (400, 401, 403, 404):
                    break
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, RuntimeError) as exc:
                error = str(exc) or type(exc).__name__
                if error in {"Rate Limited", "Invalid provider response"}:
                    break
            if attempt < self.retries:
                self._sleep(0.25 * 2**attempt)
        raise RuntimeError(error)

    @staticmethod
    def _parse(payload: dict[str, Any]) -> list[ClinicalTrialRecord]:
        records: list[ClinicalTrialRecord] = []
        seen: set[str] = set()
        for item in payload.get("studies", []):
            protocol = item.get("protocolSection", {}) if isinstance(item, dict) else {}
            identification = protocol.get("identificationModule", {})
            nct_id = str(identification.get("nctId", "")).upper()
            if not _NCT_PATTERN.fullmatch(nct_id) or nct_id in seen:
                continue
            seen.add(nct_id)
            status = protocol.get("statusModule", {})
            design = protocol.get("designModule", {})
            sponsor = protocol.get("sponsorCollaboratorsModule", {})
            conditions = protocol.get("conditionsModule", {})
            arms = protocol.get("armsInterventionsModule", {})
            phases = design.get("phases", [])
            interventions = tuple(
                str(value.get("name"))
                for value in arms.get("interventions", [])
                if isinstance(value, dict) and value.get("name")
            )
            records.append(ClinicalTrialRecord(
                nct_id=nct_id,
                title=str(identification.get("briefTitle") or identification.get("officialTitle") or "Untitled registered study"),
                status=str(status.get("overallStatus") or "NOT_PROVIDED"),
                conditions=tuple(str(value) for value in conditions.get("conditions", []) if value),
                interventions=interventions,
                phase=", ".join(str(value) for value in phases) if phases else "N/A",
                sponsor=str(sponsor.get("leadSponsor", {}).get("name") or "Not provided"),
                url=f"https://clinicaltrials.gov/study/{nct_id}",
            ))
        return records

    def _save_cache(self, query: str, records: list[ClinicalTrialRecord]) -> None:
        payload = {
            "schema": "biointel.clinical-trials-cache.v2",
            "retrieved_epoch": self._now(),
            "source": self.last_source,
            "records": [asdict(record) for record in records],
        }
        self._cache_path(query).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_cache(self, query: str) -> list[ClinicalTrialRecord]:
        path = self._cache_path(query)
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = []
            for row in payload.get("records", []):
                row["conditions"] = tuple(row.get("conditions", []))
                row["interventions"] = tuple(row.get("interventions", []))
                records.append(ClinicalTrialRecord(**row))
            self.last_retrieved_at = datetime.fromtimestamp(
                float(payload["retrieved_epoch"]), timezone.utc
            ).isoformat().replace("+00:00", "Z")
            return records
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return []

    def search_trials(
        self,
        query: str,
        limit: int = 10,
        *,
        page_token: str | None = None,
        force_refresh: bool = False,
    ) -> list[ClinicalTrialRecord]:
        """Return live or explicitly cached records; never fabricate fallback trials."""
        clean = self._validate_query(query)
        params: dict[str, Any] = {
            "query.term": clean,
            "pageSize": min(100, max(1, int(limit))),
            "format": "json",
        }
        if page_token:
            params["pageToken"] = page_token
        url = f"{self.BASE_URL}?{urllib.parse.urlencode(params)}"
        self.last_error, self.next_page_token = "", None
        try:
            payload = self._request(url)
            records = self._parse(payload)
            self.next_page_token = payload.get("nextPageToken")
            self.last_status = "Live ClinicalTrials.gov"
            self.last_retrieved_at = datetime.fromtimestamp(
                self._now(), timezone.utc
            ).isoformat().replace("+00:00", "Z")
            if not page_token:
                self._save_cache(clean, records)
            return records
        except (RuntimeError, ValueError) as exc:
            self.last_error = str(exc)
            if not force_refresh and not page_token:
                cached = self._load_cache(clean)
                if cached:
                    self.last_status = "Cached ClinicalTrials.gov"
                    return cached[: max(1, int(limit))]
            self.last_status = "Rate Limited" if "Rate Limited" in str(exc) else "ClinicalTrials.gov Unavailable"
            logger.warning("ClinicalTrials.gov search failed: %s", exc)
            return []