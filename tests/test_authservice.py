import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient

from components.authservice import (
    AuthService, HS256TokenSigner, PasswordHasher, InMemoryUserRepo,
    AuthConfig, set_auth_service, auth_router, require_scopes
)
from components.authservice.contracts import LoginRequest

def make_app():
    app = FastAPI()
    # Wire test DI
    hasher = PasswordHasher()
    repo = InMemoryUserRepo(hasher)
    user_id = str(uuid.uuid4())
    repo.add_user(
        id=user_id,
        email="alice@example.com",
        display_name="Alice",
        tenant_id="t-1",
        password="secret123",
        scopes=["documents:ingest", "chat:read"],
    )
    signer = HS256TokenSigner("test-secret", kid="k1")
    svc = AuthService(user_repo=repo, signer=signer, cfg=AuthConfig())
    set_auth_service(svc)
    app.include_router(auth_router)

    @app.get("/protected")
    def protected(user = require_scopes(["documents:ingest"])()):
        return {"ok": True, "user_id": user.id}

    return app

def test_login_refresh_and_me_flow():
    app = make_app()
    client = TestClient(app)

    # Login
    res = client.post("/auth/login", json={"email": "alice@example.com", "password": "secret123"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    access = body["result"]["access_token"]
    refresh = body["result"]["refresh_token"]

    # Me
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert res.status_code == 200
    me = res.json()
    assert me["ok"] is True
    assert me["result"]["user"]["email"] == "alice@example.com"

    # Protected with scope
    res = client.get("/protected", headers={"Authorization": f"Bearer {access}"})
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Refresh
    res = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert res.status_code == 200
    body2 = res.json()
    assert body2["ok"] is True
    assert body2["result"]["access_token"] != access  # new access token