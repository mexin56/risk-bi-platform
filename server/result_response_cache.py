"""缓存已编码的业务结果响应，发布或规则状态变化时立即换版本。"""

from collections import OrderedDict
import gzip
import hashlib
import json
from pathlib import Path
import threading

from fastapi import Request
from fastapi.responses import Response

from pipeline.business_results import file_version, snapshot_version

_CACHE = OrderedDict()
_LOCK = threading.RLock()
_MAX_ENTRIES = 24


def _accepts_gzip(request: Request) -> bool:
    qualities = {}
    for item in request.headers.get("accept-encoding", "").lower().split(","):
        parts = item.strip().split(";")
        try:
            qualities[parts[0]] = next((float(p.strip()[2:]) for p in parts[1:] if p.strip().startswith("q=")), 1.0)
        except ValueError:
            qualities[parts[0]] = 0.0
    return qualities.get("gzip", qualities.get("*", 0.0)) > 0


def cached_dashboard_response(request: Request, *, domain: str, serving_dir: Path,
                              status_path: Path, partition: str | None, offset: int,
                              force: bool, load_payload) -> Response:
    version = snapshot_version(serving_dir)
    status_version = (file_version(status_path), file_version(Path(str(status_path) + "-wal")))
    key = (domain, version, status_version, partition, int(offset))
    return cached_published_response(request, key=key, version=version, force=force, load_payload=load_payload)


def cached_published_response(request: Request, *, key: tuple, version: str, force: bool, load_payload) -> Response:
    """Reuse encoded model results until the atomically published file changes."""
    cacheable = bool(version) and not force
    with _LOCK:
        encoded = _CACHE.get(key) if cacheable else None
        if encoded is not None:
            _CACHE.move_to_end(key)
    if encoded is None:
        payload = load_payload()
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        compressed = gzip.compress(body, compresslevel=3, mtime=0)
        encoded = (body, compressed, tuple('"' + hashlib.sha256(value).hexdigest()[:24] + '"' for value in (body, compressed)))
        if cacheable and (payload.get("meta") or {}).get("result_store") == "duckdb" and not (payload.get("meta") or {}).get("async_refresh"):
            with _LOCK:
                _CACHE[key] = encoded
                _CACHE.move_to_end(key)
                while len(_CACHE) > _MAX_ENTRIES:
                    _CACHE.popitem(last=False)
    use_gzip = _accepts_gzip(request)
    body = encoded[1 if use_gzip else 0]
    tag = encoded[2][1 if use_gzip else 0]
    headers = {"ETag": tag, "Cache-Control": "no-store" if force or not cacheable else "private, no-cache",
               "Vary": "Accept-Encoding"}
    if not force and tag in [item.strip() for item in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=headers)
    if use_gzip:
        headers["Content-Encoding"] = "gzip"
    return Response(content=body, media_type="application/json", headers=headers)
