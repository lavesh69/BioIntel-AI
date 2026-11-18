from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def test_production_container_contract() -> None:
    text=(ROOT/'Dockerfile.production').read_text()
    assert 'HEALTHCHECK' in text and 'USER 10001:10001' in text and 'org.opencontainers.image' in text
    compose=(ROOT/'docker-compose.production.yml').read_text()
    assert 'read_only: true' in compose and 'cap_drop' in compose
