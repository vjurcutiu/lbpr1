# AuthService — Quick Start (dev)

## Bootstrapping in FastAPI
```python
# app.py (example)
from fastapi import FastAPI
from components.authservice import (
    AuthService, HS256TokenSigner, PasswordHasher, InMemoryUserRepo,
    AuthConfig, set_auth_service, auth_router
)

app = FastAPI()
cfg = AuthConfig()
signer = HS256TokenSigner(cfg.secret, kid="primary")
hasher = PasswordHasher()
repo = InMemoryUserRepo(hasher)
# seed dev user
repo.add_user(
    id="u-1", email="dev@example.com", display_name="Dev User",
    tenant_id="tenant-1", password="devpass", scopes=["documents:ingest","chat:read"]
)
svc = AuthService(user_repo=repo, signer=signer, cfg=cfg)
set_auth_service(svc)
app.include_router(auth_router)