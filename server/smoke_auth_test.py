"""Smoke test for the auth/permission system (run from server/)."""
import json

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def req(method, path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.request(method, path, headers=headers, **kwargs)


ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name}  {extra}")


# 1. login failures
r = req("POST", "/api/auth/login", json={"username": "admin", "password": "wrong"})
check("wrong password -> 401", r.status_code == 401, r.text)

r = req("POST", "/api/auth/login", json={"username": "nobody", "password": "x"})
check("unknown user -> 401", r.status_code == 401, r.text)

# 2. admin login
r = req("POST", "/api/auth/login", json={"username": "admin", "password": "admin123"})
check("admin login -> 200", r.status_code == 200, r.text)
admin_token = r.json()["token"]
admin_user = r.json()["user"]
check("admin has users perm", "users" in admin_user["permissions"])

# 3. no token
r = req("GET", "/api/auth/me")
check("me without token -> 401", r.status_code == 401, r.text)

r = req("GET", "/api/credit-attribution/partitions")
check("attribution without token -> 401", r.status_code == 401, r.text)

# 4. me / logout
r = req("GET", "/api/auth/me", token=admin_token)
check("me with token -> 200", r.status_code == 200 and r.json()["username"] == "admin", r.text)

# 5. admin management endpoints
r = req("GET", "/api/auth/users", token=admin_token)
check("list users -> 3 seeded", r.status_code == 200 and len(r.json()["users"]) == 3, r.text)

r = req("GET", "/api/auth/roles", token=admin_token)
roles = r.json()["roles"]
check("list roles -> 3 seeded", r.status_code == 200 and len(roles) == 3, r.text)
check("role admin builtin", any(x["key"] == "admin" and x["builtin"] for x in roles))

r = req("GET", "/api/auth/permissions", token=admin_token)
check("permission catalog -> 10", r.status_code == 200 and len(r.json()["permissions"]) == 10, r.text)

# 6. analyst login + permission guard
r = req("POST", "/api/auth/login", json={"username": "analyst", "password": "analyst123"})
check("analyst login", r.status_code == 200, r.text)
analyst_token = r.json()["token"]
check("analyst lacks users perm", "users" not in r.json()["user"]["permissions"])

r = req("GET", "/api/auth/users", token=analyst_token)
check("analyst /users -> 403", r.status_code == 403, r.text)

r = req("GET", "/api/credit-attribution/partitions", token=analyst_token)
check("analyst attribution -> 200 (perm ok)", r.status_code == 200, r.text)

# 7. viewer login + guards
r = req("POST", "/api/auth/login", json={"username": "viewer", "password": "viewer123"})
check("viewer login", r.status_code == 200, r.text)
viewer_token = r.json()["token"]
check("viewer lacks attribution perm", "attribution" not in r.json()["user"]["permissions"])

r = req("GET", "/api/credit-attribution/partitions", token=viewer_token)
check("viewer attribution -> 403", r.status_code == 403, r.text)

# 8. create / update / delete user
r = req(
    "POST",
    "/api/auth/users",
    token=admin_token,
    json={"username": "risk_ops", "display_name": "风控运营", "password": "ops123456", "role_key": "viewer", "enabled": True},
)
check("create user -> 201", r.status_code == 201, r.text)
new_id = r.json()["id"]

r = req("POST", "/api/auth/users", token=admin_token,
        json={"username": "risk_ops", "display_name": "x", "password": "ops123456", "role_key": "viewer"})
check("duplicate username -> 409", r.status_code == 409, r.text)

r = req("PUT", f"/api/auth/users/{new_id}", token=admin_token,
        json={"role_key": "analyst", "display_name": "风控运营组"})
check("update user -> role changed", r.status_code == 200 and r.json()["role_key"] == "analyst", r.text)

r = req("PUT", f"/api/auth/users/{new_id}", token=admin_token, json={"password": "newpass888"})
check("reset password", r.status_code == 200, r.text)

r = req("POST", "/api/auth/login", json={"username": "risk_ops", "password": "newpass888"})
check("login with new password", r.status_code == 200, r.text)

r = req("DELETE", f"/api/auth/users/{new_id}", token=admin_token)
check("delete user", r.status_code == 200, r.text)

# 9. cannot delete self / disable self
admin_id = admin_user["id"]
r = req("DELETE", f"/api/auth/users/{admin_id}", token=admin_token)
check("cannot delete self -> 400", r.status_code == 400, r.text)

r = req("PUT", f"/api/auth/users/{admin_id}", token=admin_token, json={"enabled": False})
check("cannot disable self -> 400", r.status_code == 400, r.text)

# 10. role CRUD
r = req("POST", "/api/auth/roles", token=admin_token,
        json={"key": "risk_ops", "name": "风控运营", "permissions": ["overview", "channel"]})
check("create role -> 201", r.status_code == 201, r.text)

r = req("PUT", "/api/auth/roles/risk_ops", token=admin_token,
        json={"permissions": ["overview", "channel", "fraud"], "name": "风控运营组"})
check("update role permissions", r.status_code == 200, r.text)

r = req("DELETE", "/api/auth/roles/risk_ops", token=admin_token)
check("delete role", r.status_code == 200, r.text)

r = req("DELETE", "/api/auth/roles/admin", token=admin_token)
check("cannot delete builtin role -> 400", r.status_code == 400, r.text)

r = req("PUT", "/api/auth/roles/analyst", token=admin_token, json={"permissions": ["overview", "bogus"]})
check("invalid permission -> 400", r.status_code == 400, r.text)

# 11. permission change takes effect immediately for analyst
r = req("PUT", "/api/auth/roles/analyst", token=admin_token,
        json={"permissions": ["overview", "lifecycle", "attribution", "channel", "fraud", "vintage", "model", "stability", "creditStrategy"]})
check("strip analyst users perm", r.status_code == 200, r.text)

# 12. logout invalidates token
r = req("POST", "/api/auth/logout", token=admin_token)
check("logout -> 200", r.status_code == 200, r.text)
r = req("GET", "/api/auth/me", token=admin_token)
check("token invalid after logout -> 401", r.status_code == 401, r.text)

print(f"\n===== {ok} passed, {fail} failed =====")
raise SystemExit(1 if fail else 0)
