"""Protected API routes require a separate service token."""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.auth import require_service_token
from api.main_api import app


PROTECTED_PATHS = {
    "/analysis",
    "/feedback_analysis",
    "/generate_report",
    "/dify/analyze",
    "/download/{filename}",
}


def credentials(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_sensitive_routes_have_auth_dependency():
    paths = app.openapi()["paths"]
    for path in PROTECTED_PATHS:
        assert next(iter(paths[path].values()))["security"] == [{"HTTPBearer": []}]
    assert "security" not in paths["/"]["get"]


def test_auth_fails_closed_without_configuration(monkeypatch):
    monkeypatch.delenv("SERVICE_API_KEY", raising=False)
    with pytest.raises(HTTPException) as error:
        require_service_token(credentials("anything"))
    assert error.value.status_code == 503


def test_auth_accepts_only_matching_bearer_token(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", "test-service-token")
    for supplied in (
        None,
        credentials("wrong-token"),
        HTTPAuthorizationCredentials(scheme="Basic", credentials="test-service-token"),
    ):
        with pytest.raises(HTTPException) as error:
            require_service_token(supplied)
        assert error.value.status_code == 401
    assert require_service_token(credentials("test-service-token")) is None
