from fastapi.testclient import TestClient

from biointel.api.main import app


def test_core_api_contracts() -> None:
    client = TestClient(app)
    for route in (
        "/live",
        "/ready",
        "/quality/scorecard",
        "/quality/capability-readiness",
        "/production/configuration",
        "/quality/engineering-readiness",
        "/quality/engineering-gates",
    ):
        response = client.get(route)
        assert response.status_code == 200, (route, response.text)
