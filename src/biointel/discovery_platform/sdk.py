from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from .models import ProjectCreate
from .service import DiscoveryPlatformService


class BioIntelSDKError(RuntimeError):
    """Structured failure returned by a remote BioIntel research API."""

    def __init__(self, message: str, *, status_code: int = 0, detail: Any = None):
        super().__init__(message)
        self.status_code = int(status_code)
        self.detail = detail


class BioIntelResearchClient:
    """Python SDK for local-first or HTTP research-platform access."""

    api_prefix = "/v1/research-platform"

    def __init__(
        self,
        *,
        service: DiscoveryPlatformService | None = None,
        base_url: str | None = None,
        api_key: str = "",
        timeout: float = 30.0,
    ):
        if (service is None) == (base_url is None):
            raise ValueError("Provide exactly one of service or base_url")
        self.service = service
        self.base_url = str(base_url or "").rstrip("/")
        self.api_key = str(api_key)
        self.timeout = float(timeout)

    @classmethod
    def local(
        cls,
        database_path: str | Path | None = None,
        artifact_root: str | Path | None = None,
        *,
        project_root: str | Path | None = None,
        actor: str = "sdk_user",
        role: str = "Administrator",
    ) -> "BioIntelResearchClient":
        return cls(
            service=DiscoveryPlatformService(
                database_path,
                artifact_root,
                project_root=project_root,
                actor=actor,
                role=role,
            )
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        raw: bool = False,
    ) -> Any:
        import httpx

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        response = httpx.request(
            method,
            self.base_url + self.api_prefix + path,
            json=dict(json_body) if json_body is not None else None,
            params={key: value for key, value in dict(params or {}).items() if value is not None},
            headers=headers,
            timeout=self.timeout,
        )
        if response.is_error:
            try:
                detail = response.json()
            except ValueError:
                detail = {"message": response.text[:2000]}
            error = detail.get("detail", detail) if isinstance(detail, dict) else detail
            if isinstance(error, dict) and isinstance(error.get("error"), dict):
                message = str(error["error"].get("message") or error["error"])
            else:
                message = str(error)
            raise BioIntelSDKError(
                message, status_code=response.status_code, detail=detail
            )
        return response if raw else response.json()

    @staticmethod
    def _items(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return list(payload["items"])
        if isinstance(payload, list):
            return list(payload)
        raise BioIntelSDKError("API response did not contain an item list")

    def create_project(self, **values: Any) -> dict[str, Any]:
        if self.service is not None:
            return self.service.create_project(ProjectCreate(**values))
        return self._request("POST", "/projects", json_body=values)

    def list_projects(
        self, *, limit: int = 100, offset: int = 0, stage: str | None = None
    ) -> list[dict[str, Any]]:
        if self.service is not None:
            return self.service.list_projects(limit=limit, offset=offset, stage=stage)
        return self._items(
            self._request(
                "GET", "/projects",
                params={"limit": limit, "offset": offset, "stage": stage},
            )
        )

    def get_project(self, project_id: str) -> dict[str, Any]:
        if self.service is not None:
            return self.service.get_project(project_id)
        return self._request("GET", f"/projects/{project_id}")

    def register_dataset(self, project_id: str, **values: Any) -> dict[str, Any]:
        if self.service is not None:
            return self.service.register_dataset(project_id, **values)
        return self._request(
            "POST", f"/projects/{project_id}/datasets", json_body=values
        )

    def list_datasets(
        self, project_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        if self.service is not None:
            return self.service.list_datasets(project_id, limit=limit, offset=offset)
        return self._items(
            self._request(
                "GET", f"/projects/{project_id}/datasets",
                params={"limit": limit, "offset": offset},
            )
        )

    def add_samples(
        self, dataset_id: str, samples: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        rows = [dict(item) for item in samples]
        if self.service is not None:
            return self.service.add_samples(dataset_id, rows)
        return self._request(
            "POST", f"/datasets/{dataset_id}/samples", json_body={"samples": rows}
        )

    def run_analysis(
        self,
        project_id: str,
        module_id: str,
        rows: pd.DataFrame | Sequence[Mapping[str, Any]],
        *,
        parameters: Mapping[str, Any] | None = None,
        dataset_id: str | None = None,
        is_synthetic: bool = False,
        seed: int | None = None,
    ) -> dict[str, Any]:
        frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
        if self.service is not None:
            return self.service.analysis.run_and_persist(
                project_id=project_id,
                module_id=module_id,
                frame=frame,
                parameters=parameters,
                dataset_id=dataset_id,
                is_synthetic=is_synthetic,
                seed=seed,
            )
        return self._request(
            "POST",
            "/analysis-runs",
            json_body={
                "project_id": project_id,
                "module_id": module_id,
                "rows": frame.to_dict(orient="records"),
                "parameters": dict(parameters or {}),
                "dataset_id": dataset_id,
                "is_synthetic": is_synthetic,
                "seed": seed,
            },
        )

    def create_candidate(self, project_id: str, **values: Any) -> dict[str, Any]:
        if self.service is not None:
            return self.service.create_candidate(project_id, **values)
        return self._request(
            "POST", f"/projects/{project_id}/candidates", json_body=values
        )

    def list_candidates(self, project_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if self.service is not None:
            return self.service.list_candidates(project_id, limit=limit)
        return self._items(
            self._request(
                "GET", f"/projects/{project_id}/candidates", params={"limit": limit}
            )
        )

    def add_evidence(self, project_id: str, **values: Any) -> dict[str, Any]:
        if self.service is not None:
            return self.service.add_evidence(project_id, **values)
        return self._request(
            "POST", f"/projects/{project_id}/evidence", json_body=values
        )

    def create_hypothesis(self, project_id: str, **values: Any) -> dict[str, Any]:
        if self.service is not None:
            return self.service.create_hypothesis(project_id, **values)
        return self._request(
            "POST", f"/projects/{project_id}/hypotheses", json_body=values
        )

    def create_report(
        self,
        project_id: str,
        *,
        title: str,
        selected_sections: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if self.service is not None:
            return self.service.reports.create_report(
                project_id, title=title, selected_sections=selected_sections
            )
        return self._request(
            "POST", f"/projects/{project_id}/reports",
            json_body={"title": title, "selected_sections": selected_sections},
        )

    def render_report(self, report_id: str, output_format: str) -> tuple[bytes, str, str]:
        if self.service is not None:
            return self.service.reports.render(report_id, output_format)
        response = self._request(
            "GET", f"/reports/{report_id}/export/{output_format}", raw=True
        )
        disposition = response.headers.get("content-disposition", "")
        match = re.search(r'filename="?([^";]+)', disposition)
        filename = match.group(1) if match else f"{report_id}.{output_format}"
        return response.content, filename, response.headers.get(
            "content-type", "application/octet-stream"
        )

    def system_health(self) -> dict[str, Any]:
        if self.service is not None:
            return self.service.health.snapshot()
        return self._request("GET", "/system/health")


__all__ = ["BioIntelResearchClient", "BioIntelSDKError"]
