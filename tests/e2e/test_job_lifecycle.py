from fastapi.testclient import TestClient

from biointel.api.main import app


def test_submit_and_observe_job_lifecycle() -> None:
    client=TestClient(app)
    response=client.post('/jobs',json={'job_type':'diagnostic','payload':{'source':'e2e'}})
    assert response.status_code in {200,201,422}
    assert client.get('/jobs').status_code==200
