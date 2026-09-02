import base64

import pytest

pytestmark = pytest.mark.slow

_CREDS = {"Authorization": "Basic " + base64.b64encode(b"admin:secret").decode()}


@pytest.fixture
def client(data_dir, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    from starlette.testclient import TestClient

    from web.app import app

    return TestClient(app)


def test_graphql_post_requires_auth(client):
    resp = client.post("/graphql", json={"query": "{ draftClasses { name } }"})
    assert resp.status_code == 401
    assert resp.text == "Authentication required"
    assert "www-authenticate" not in {k.lower() for k in resp.headers}


def test_graphql_post_passes_with_credentials(client):
    resp = client.post(
        "/graphql", json={"query": "{ draftClasses { name } }"}, headers=_CREDS
    )
    assert resp.status_code == 200


def test_wrong_password_rejected(client):
    bad = {"Authorization": "Basic " + base64.b64encode(b"admin:nope").decode()}
    resp = client.post("/graphql", json={"query": "{ draftClasses { name } }"}, headers=bad)
    assert resp.status_code == 401


def test_healthz_is_protected(client):
    assert client.get("/healthz").status_code == 401
    assert client.get("/healthz", headers=_CREDS).status_code == 200


def test_spa_shell_is_public(client):
    # No built frontend in the test env, so this 404s - the point is that the
    # auth middleware lets it through rather than returning 401.
    assert client.get("/login").status_code != 401


def test_options_preflight_not_blocked(client):
    assert client.options("/graphql").status_code != 401
