from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

import httpx


@dataclass(frozen=True)
class ConnectorConfiguration:
    base_url: str
    bearer_token: str = ""
    api_key: str = ""
    timeout_seconds: float = 20.0
    verify_tls: bool = True
    allow_local_http: bool = False


class ClinicalConnector:
    def __init__(
        self,
        configuration: ConnectorConfiguration,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(configuration.base_url)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not (local and configuration.allow_local_http):
            raise ValueError("Clinical connectors require HTTPS except explicit localhost testing.")
        if not parsed.hostname:
            raise ValueError("Connector base URL has no host.")
        self.configuration = configuration
        self.host = parsed.hostname.lower()
        headers = {"Accept": "application/json", "User-Agent": "BioIntel-AI/15.6.0 Step217"}
        if configuration.bearer_token:
            headers["Authorization"] = f"Bearer {configuration.bearer_token}"
        if configuration.api_key:
            headers["X-API-Key"] = configuration.api_key
        self.client = httpx.Client(
            base_url=configuration.base_url.rstrip("/") + "/",
            headers=headers,
            timeout=max(1.0, min(configuration.timeout_seconds, 120.0)),
            verify=configuration.verify_tls,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = urljoin(str(self.client.base_url), path.lstrip("/"))
        if (urlsplit(url).hostname or "").lower() != self.host:
            raise ValueError("Connector request escaped the configured host.")
        response = self.client.request(method, url, **kwargs)
        response.raise_for_status()
        if int(response.headers.get("content-length", "0") or 0) > 50_000_000:
            raise ValueError("Connector response exceeds the 50 MB safety limit.")
        return response.json()


class FhirConnector(ClinicalConnector):
    def capability_statement(self) -> dict[str, Any]:
        value = self._request("GET", "metadata", headers={"Accept": "application/fhir+json"})
        if value.get("resourceType") != "CapabilityStatement":
            raise ValueError("FHIR server did not return a CapabilityStatement.")
        return value

    def read(self, resource_type: str, resource_id: str) -> dict[str, Any]:
        if not resource_type.replace("_", "").isalnum() or not resource_id.replace("-", "").isalnum():
            raise ValueError("Unsafe FHIR resource identifier.")
        value = self._request("GET", f"{resource_type}/{resource_id}", headers={"Accept": "application/fhir+json"})
        if value.get("resourceType") != resource_type:
            raise ValueError("FHIR resource type mismatch.")
        return value

    def search(self, resource_type: str, parameters: Mapping[str, str]) -> dict[str, Any]:
        if not resource_type.replace("_", "").isalnum():
            raise ValueError("Unsafe FHIR resource type.")
        value = self._request(
            "GET",
            resource_type,
            params={str(key): str(item) for key, item in parameters.items()},
            headers={"Accept": "application/fhir+json"},
        )
        if value.get("resourceType") != "Bundle":
            raise ValueError("FHIR search did not return a Bundle.")
        return value


class DicomWebConnector(ClinicalConnector):
    def studies(self, parameters: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
        value = self._request(
            "GET",
            "studies",
            params=dict(parameters or {}),
            headers={"Accept": "application/dicom+json"},
        )
        if not isinstance(value, list):
            raise ValueError("DICOMweb QIDO-RS response must be a list.")
        return [item for item in value if isinstance(item, dict)]


class RedcapConnector(ClinicalConnector):
    def export_records(
        self,
        project_token: str,
        *,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        form: list[tuple[str, str]] = [
            ("token", project_token),
            ("content", "record"),
            ("format", "json"),
            ("type", "flat"),
            ("rawOrLabel", "raw"),
        ]
        form.extend(("fields[]", value) for value in (fields or []))
        value = self._request("POST", "", data=form)
        if not isinstance(value, list):
            raise ValueError("REDCap record export must be a list.")
        return [item for item in value if isinstance(item, dict)]


class LimsConnector(ClinicalConnector):
    def health(self) -> dict[str, Any]:
        value = self._request("GET", "health")
        if not isinstance(value, dict):
            raise ValueError("LIMS health response must be an object.")
        return value

    def samples(self, parameters: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
        value = self._request("GET", "samples", params=dict(parameters or {}))
        if isinstance(value, dict):
            value = value.get("items", [])
        if not isinstance(value, list):
            raise ValueError("LIMS sample response must be a list.")
        return [item for item in value if isinstance(item, dict)]
