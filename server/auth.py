"""风控BI平台 · 登录与会话/权限管理。

轻量自包含实现（仅标准库 + FastAPI，不新增第三方依赖）：
- 用户/角色/会话存 SQLite（server/data/rcbi.db，已被 .gitignore 忽略）
- 密码使用 PBKDF2-HMAC-SHA256 加盐哈希，不存明文
- 会话为随机 token，带过期时间，登出即失效
- 页面权限挂在角色上；接口层通过 require_perm 强制校验，
  角色权限修改后对所有该角色用户即时生效
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "rcbi.db"
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "43200"))  # 默认 12 小时
PBKDF2_ITERATIONS = 120_000

# 页面权限目录：与前端 src/lib/auth.ts 的 PAGE_PERMISSIONS 保持一致
PERMISSION_CATALOG = [
    {"key": "overview", "label": "大盘数据"},
    {"key": "lifecycle", "label": "客户生命周期"},
    {"key": "creditStrategy", "label": "提额策略监控"},
    {"key": "attribution", "label": "授信归因监控"},
    {"key": "fundMonitor", "label": "资金归结监控"},
    {"key": "channel", "label": "渠道质量"},
    {"key": "fraud", "label": "反欺诈监控"},
    {"key": "vintage", "label": "Vintage 监控"},
    {"key": "model", "label": "模型分监控"},
    {"key": "stability", "label": "模型稳定性"},
    {"key": "users", "label": "权限管理"},
]
ALL_PERMISSIONS = [item["key"] for item in PERMISSION_CATALOG]
MONITOR_PERMISSIONS = [key for key in ALL_PERMISSIONS if key != "users"]

DEFAULT_ROLES = [
    ("admin", "管理员", ALL_PERMISSIONS, True),
    ("analyst", "分析师", MONITOR_PERMISSIONS, True),
    ("viewer", "访客", ["overview", "lifecycle", "channel", "vintage", "model", "stability"], True),
]

# (username, display_name, role_key, env_password, default_password)
DEFAULT_USERS = [
    ("admin", "系统管理员", "admin", "AUTH_ADMIN_PASSWORD", "admin123"),
    ("analyst", "风控分析师", "analyst", "AUTH_ANALYST_PASSWORD", "analyst123"),
    ("viewer", "只读访客", "viewer", "AUTH_VIEWER_PASSWORD", "viewer123"),
]

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{2,32}$")
ROLE_KEY_RE = re.compile(r"^[A-Za-z0-9_]{2,24}$")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
        _seed(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role_key TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        );
        CREATE TABLE IF NOT EXISTS roles (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            permissions TEXT NOT NULL DEFAULT '[]',
            builtin INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
        """
    )
    conn.commit()


def _seed(conn: sqlite3.Connection) -> None:
    for key, name, permissions, builtin in DEFAULT_ROLES:
        conn.execute(
            "INSERT OR IGNORE INTO roles (key, name, permissions, builtin) VALUES (?, ?, ?, ?)",
            (key, name, json.dumps(permissions), int(builtin)),
        )
    _grant_new_permissions(conn)
    count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count == 0:
        for username, display_name, role_key, env_name, default_password in DEFAULT_USERS:
            password = os.getenv(env_name, default_password)
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, role_key, enabled, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (username, display_name, hash_password(password), role_key, _now()),
            )
    conn.commit()


def _grant_new_permissions(conn: sqlite3.Connection) -> None:
    """新增页面权限时自动授予 admin/analyst 内置角色（对既有库平滑升级）。

    只补充"当前任何角色都没有的权限 key"（即新目录项），不会恢复被管理员
    主动移除的权限。
    """
    known: set[str] = set()
    for row in conn.execute("SELECT permissions FROM roles").fetchall():
        try:
            known.update(json.loads(row["permissions"] or "[]"))
        except (ValueError, TypeError):
            continue
    fresh = [key for key in ALL_PERMISSIONS if key not in known]
    if not fresh:
        return
    for role_key in ("admin", "analyst"):
        row = conn.execute("SELECT permissions FROM roles WHERE key = ?", [role_key]).fetchone()
        if row is None:
            continue
        permissions = json.loads(row["permissions"] or "[]")
        merged = list(dict.fromkeys([*permissions, *fresh]))
        conn.execute("UPDATE roles SET permissions = ? WHERE key = ?", [json.dumps(merged), role_key])


def create_session(username: str) -> str:
    token = secrets.token_hex(24)
    now = datetime.now(timezone.utc)
    with _lock:
        conn = db()
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (_now(),))
        conn.execute(
            "INSERT INTO sessions (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (
                token,
                username,
                now.isoformat(timespec="seconds"),
                (now + timedelta(seconds=TOKEN_TTL_SECONDS)).isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
    return token


def user_by_token(token: str | None) -> dict[str, Any] | None:
    """按 token 取用户，权限实时从角色表读取（修改权限即时生效）。"""
    if not token:
        return None
    row = db().execute(
        "SELECT u.id, u.username, u.display_name, u.role_key, u.enabled, u.created_at, u.last_login_at, "
        "r.name AS role_name, r.permissions AS permissions "
        "FROM sessions s JOIN users u ON u.username = s.username "
        "JOIN roles r ON r.key = u.role_key "
        "WHERE s.token = ? AND s.expires_at > ?",
        (token, _now()),
    ).fetchone()
    if row is None:
        return None
    user = dict(row)
    user["permissions"] = json.loads(user["permissions"] or "[]")
    user["enabled"] = bool(user["enabled"])
    return user


def user_payload(username: str) -> dict[str, Any]:
    row = db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    role = db().execute("SELECT * FROM roles WHERE key = ?", (row["role_key"],)).fetchone()
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role_key": role["key"],
        "role_name": role["name"],
        "permissions": json.loads(role["permissions"] or "[]"),
        "enabled": bool(row["enabled"]),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    user = user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录。")
    if not user["enabled"]:
        raise HTTPException(status_code=401, detail="账号已被禁用，请联系管理员。")
    return user


def require_perm(permission: str):
    """接口级权限校验依赖；管理员角色始终拥有全部权限。"""

    def dependency(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user["role_key"] != "admin" and permission not in user["permissions"]:
            raise HTTPException(status_code=403, detail="当前账号无权访问该功能。")
        return user

    return dependency


def _validate_permissions(permissions: list[str]) -> list[str]:
    unknown = [p for p in permissions if p not in ALL_PERMISSIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"包含未知权限：{', '.join(unknown)}")
    return list(dict.fromkeys(permissions))


# ==================== 请求模型 ====================

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    display_name: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    role_key: str = Field(min_length=2, max_length=24)
    enabled: bool = True


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=32)
    role_key: str | None = Field(default=None, min_length=2, max_length=24)
    enabled: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=64)


class RoleCreate(BaseModel):
    key: str = Field(min_length=2, max_length=24)
    name: str = Field(min_length=1, max_length=24)
    permissions: list[str] = []


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=24)
    permissions: list[str] | None = None


# ==================== 路由 ====================

router = APIRouter()


@router.post("/login")
def login(body: LoginRequest) -> dict[str, Any]:
    username = body.username.strip()
    row = db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误。")
    if not row["enabled"]:
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员。")
    token = create_session(row["username"])
    with _lock:
        conn = db()
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), row["id"]))
        conn.commit()
    return {"token": token, "user": user_payload(row["username"])}


@router.post("/logout")
def logout(
    user: dict[str, Any] = Depends(current_user),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    if token:
        with _lock:
            conn = db()
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
    return {"ok": True}


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@router.get("/users")
def list_users(_user: dict[str, Any] = Depends(require_perm("users"))) -> dict[str, Any]:
    rows = db().execute(
        "SELECT u.id, u.username, u.display_name, u.role_key, u.enabled, u.created_at, u.last_login_at, "
        "r.name AS role_name "
        "FROM users u JOIN roles r ON r.key = u.role_key ORDER BY u.id"
    ).fetchall()
    return {"users": [dict(row) for row in rows]}


@router.post("/users", status_code=201)
def create_user(body: UserCreate, _user: dict[str, Any] = Depends(require_perm("users"))) -> dict[str, Any]:
    username = body.username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=400, detail="用户名仅支持字母、数字、下划线，长度 2-32。")
    role = db().execute("SELECT key FROM roles WHERE key = ?", (body.role_key,)).fetchone()
    if role is None:
        raise HTTPException(status_code=400, detail="所选角色不存在。")
    if db().execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        raise HTTPException(status_code=409, detail="用户名已存在。")
    with _lock:
        conn = db()
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role_key, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                username,
                body.display_name.strip(),
                hash_password(body.password),
                body.role_key,
                int(body.enabled),
                _now(),
            ),
        )
        conn.commit()
    return user_payload(username)


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    current: dict[str, Any] = Depends(require_perm("users")),
) -> dict[str, Any]:
    with _lock:
        conn = db()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在。")
        if body.role_key is not None and not conn.execute(
            "SELECT 1 FROM roles WHERE key = ?", (body.role_key,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="所选角色不存在。")
        if body.enabled is False and row["username"] == current["username"]:
            raise HTTPException(status_code=400, detail="不能禁用当前登录账号。")
        updates: list[str] = []
        params: list[Any] = []
        if body.display_name is not None:
            updates.append("display_name = ?")
            params.append(body.display_name.strip())
        if body.role_key is not None:
            updates.append("role_key = ?")
            params.append(body.role_key)
        if body.enabled is not None:
            updates.append("enabled = ?")
            params.append(int(body.enabled))
        if body.password is not None:
            updates.append("password_hash = ?")
            params.append(hash_password(body.password))
        if updates:
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
    return user_payload(row["username"])


@router.delete("/users/{user_id}")
def delete_user(user_id: int, current: dict[str, Any] = Depends(require_perm("users"))) -> dict[str, Any]:
    with _lock:
        conn = db()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="用户不存在。")
        if row["username"] == current["username"]:
            raise HTTPException(status_code=400, detail="不能删除当前登录账号。")
        admin_count = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role_key = 'admin' AND enabled = 1"
        ).fetchone()["c"]
        if row["role_key"] == "admin" and admin_count <= 1:
            raise HTTPException(status_code=400, detail="至少保留一名启用的管理员账号。")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM sessions WHERE username = ?", (row["username"],))
        conn.commit()
    return {"ok": True}


@router.get("/roles")
def list_roles(_user: dict[str, Any] = Depends(require_perm("users"))) -> dict[str, Any]:
    rows = db().execute(
        "SELECT r.*, (SELECT COUNT(*) FROM users u WHERE u.role_key = r.key) AS user_count "
        "FROM roles r ORDER BY r.builtin DESC, r.key"
    ).fetchall()
    roles = []
    for row in rows:
        item = dict(row)
        item["permissions"] = json.loads(item["permissions"] or "[]")
        item["builtin"] = bool(item["builtin"])
        roles.append(item)
    return {"roles": roles}


@router.post("/roles", status_code=201)
def create_role(body: RoleCreate, _user: dict[str, Any] = Depends(require_perm("users"))) -> dict[str, Any]:
    key = body.key.strip().lower()
    if not ROLE_KEY_RE.fullmatch(key):
        raise HTTPException(status_code=400, detail="角色标识仅支持字母、数字、下划线，长度 2-24。")
    if db().execute("SELECT 1 FROM roles WHERE key = ?", (key,)).fetchone():
        raise HTTPException(status_code=409, detail="角色标识已存在。")
    permissions = _validate_permissions(body.permissions)
    with _lock:
        conn = db()
        conn.execute(
            "INSERT INTO roles (key, name, permissions, builtin) VALUES (?, ?, ?, 0)",
            (key, body.name.strip(), json.dumps(permissions)),
        )
        conn.commit()
    return {"ok": True}


@router.put("/roles/{key}")
def update_role(
    key: str,
    body: RoleUpdate,
    _user: dict[str, Any] = Depends(require_perm("users")),
) -> dict[str, Any]:
    with _lock:
        conn = db()
        row = conn.execute("SELECT * FROM roles WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="角色不存在。")
        updates: list[str] = []
        params: list[Any] = []
        if body.name is not None:
            updates.append("name = ?")
            params.append(body.name.strip())
        if body.permissions is not None:
            updates.append("permissions = ?")
            params.append(json.dumps(_validate_permissions(body.permissions)))
        if updates:
            params.append(key)
            conn.execute(f"UPDATE roles SET {', '.join(updates)} WHERE key = ?", params)
            conn.commit()
    return {"ok": True}


@router.delete("/roles/{key}")
def delete_role(key: str, _user: dict[str, Any] = Depends(require_perm("users"))) -> dict[str, Any]:
    with _lock:
        conn = db()
        row = conn.execute("SELECT * FROM roles WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="角色不存在。")
        if row["builtin"]:
            raise HTTPException(status_code=400, detail="内置角色不可删除。")
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role_key = ?", (key,)
        ).fetchone()["c"]
        if count:
            raise HTTPException(status_code=400, detail=f"该角色下仍有 {count} 名用户，无法删除。")
        conn.execute("DELETE FROM roles WHERE key = ?", (key,))
        conn.commit()
    return {"ok": True}


@router.get("/permissions")
def permission_catalog(_user: dict[str, Any] = Depends(require_perm("users"))) -> dict[str, Any]:
    return {"permissions": PERMISSION_CATALOG}
