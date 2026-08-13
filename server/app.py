"""授信归因监控 API。

AK/SK 只在服务端读取：优先使用部署环境变量；本地开发可从指定 notebook
静态读取 ODPS(AK, SK, project, endpoint) 的字面量参数。不会执行 notebook，
不会向浏览器返回或写入 AK/SK。
"""

from __future__ import annotations

import ast
import copy
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from warehouse import WarehouseAttributionRunner

try:
    from odps import ODPS
except ImportError:  # pragma: no cover
    ODPS = None  # type: ignore[assignment,misc]


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "attribution_config.json"
LOCAL_ENV_PATH = ROOT / ".env.local"
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")
SAFE_PARTITION = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_RECORD_ID = re.compile(r"^[0-9a-f]{12}$")
CACHE_SECONDS = int(os.getenv("ATTRIBUTION_CACHE_SECONDS", "900"))


class AttributionServiceError(RuntimeError):
    """A configuration/data-source failure that is safe to expose to the UI."""


@dataclass(frozen=True)
class MaxComputeConnection:
    access_key_id: str
    access_key_secret: str
    project: str
    endpoint: str


def load_local_env() -> None:
    """Load git-ignored server/.env.local without adding a dotenv dependency."""
    if not LOCAL_ENV_PATH.exists():
        return
    for raw_line in LOCAL_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _literal_string(node: ast.AST, label: str) -> str:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        raise AttributionServiceError(f"Notebook 中的 {label} 不是静态字符串，无法安全读取。")
    return node.value


def read_connection_from_notebook(path: Path) -> MaxComputeConnection:
    """Read literal ODPS arguments only; untrusted notebook code is never executed."""
    if not path.exists():
        raise AttributionServiceError(f"未找到连接 notebook：{path}")
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AttributionServiceError("无法解析 MaxCompute 连接 notebook。") from exc

    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        try:
            tree = ast.parse("".join(cell.get("source", [])))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name != "ODPS" or len(node.args) < 3:
                continue
            endpoint = next((keyword.value for keyword in node.keywords if keyword.arg == "endpoint"), None)
            if endpoint is None:
                continue
            return MaxComputeConnection(
                access_key_id=_literal_string(node.args[0], "Access Key ID"),
                access_key_secret=_literal_string(node.args[1], "Access Key Secret"),
                project=_literal_string(node.args[2], "project"),
                endpoint=_literal_string(endpoint, "endpoint"),
            )
    raise AttributionServiceError("Notebook 中未找到可用的 ODPS(AK, SK, project, endpoint) 调用。")


def get_connection() -> MaxComputeConnection:
    values = {
        "access_key_id": os.getenv("MAXCOMPUTE_ACCESS_KEY_ID", "").strip(),
        "access_key_secret": os.getenv("MAXCOMPUTE_ACCESS_KEY_SECRET", "").strip(),
        "project": os.getenv("MAXCOMPUTE_PROJECT", "").strip(),
        "endpoint": os.getenv("MAXCOMPUTE_ENDPOINT", "").strip(),
    }
    if all(values.values()):
        return MaxComputeConnection(**values)

    notebook_path = os.getenv("MAXCOMPUTE_NOTEBOOK_PATH", "").strip()
    if not notebook_path:
        raise AttributionServiceError(
            "未配置 MaxCompute 凭据。请设置 MAXCOMPUTE_* 环境变量，或在 server/.env.local 中设置 MAXCOMPUTE_NOTEBOOK_PATH。"
        )
    return read_connection_from_notebook(Path(notebook_path).expanduser())


def json_safe(value: Any) -> Any:
    """Convert rare numpy/pandas scalar results without exposing internal objects."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            pass
    return value


class AttributionService:
    def __init__(self) -> None:
        self.config = load_config()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._path_trend_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
        self._partition_cache: tuple[float, list[str]] | None = None
        self._lock = threading.Lock()

    @property
    def table_name(self) -> str:
        table = os.getenv("MAXCOMPUTE_TABLE", self.config["table"]).strip()
        if not SAFE_IDENTIFIER.fullmatch(table):
            raise AttributionServiceError("MAXCOMPUTE_TABLE 格式不合法。")
        return table

    def _odps(self) -> Any:
        if ODPS is None:
            raise AttributionServiceError("未安装 pyodps。请执行 python -m pip install -r server/requirements.txt。")
        connection = get_connection()
        return ODPS(
            connection.access_key_id,
            connection.access_key_secret,
            project=connection.project,
            endpoint=connection.endpoint,
        )

    def available_partitions(self) -> list[str]:
        cached = self._partition_cache
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return list(cached[1])

        odps = self._odps()
        table = odps.get_table(self.table_name.split(".")[-1])
        partitions: list[str] = []
        for partition in table.partitions:
            match = re.search(r"pt='([^']+)'", str(partition))
            if match:
                partitions.append(match.group(1))
        result = sorted(set(partitions), reverse=True)
        self._partition_cache = (time.time(), result)
        return result

    def _run_sql_rows(self, sql: str) -> list[dict[str, Any]]:
        """Pair-safe PyODPS Record extraction for compact daily aggregation results."""
        odps = self._odps()
        instance = odps.execute_sql(sql)
        rows: list[dict[str, Any]] = []
        with instance.open_reader(tunnel=True, limit=False) as reader:
            columns = [column.name for column in reader.schema.columns]
            for record in reader:
                row: dict[str, Any] = {}
                for index, name in enumerate(columns):
                    try:
                        row[name] = record[name]
                    except Exception:
                        row[name] = record[index]
                rows.append(row)
        return rows

    def dashboard(self, partition: str | None = None, force: bool = False) -> dict[str, Any]:
        partitions = self.available_partitions()
        if not partitions:
            raise AttributionServiceError("目标表未找到可用 pt 分区。")
        selected = partition or partitions[0]
        if not SAFE_PARTITION.fullmatch(selected) or selected not in partitions:
            raise AttributionServiceError(f"分区 pt={selected} 不存在或格式不合法。")

        if force:
            for cache_key in [key for key in self._path_trend_cache if key[0] == selected]:
                self._path_trend_cache.pop(cache_key, None)

        cached = self._cache.get(selected)
        if cached and not force and time.time() - cached[0] < CACHE_SECONDS:
            result = copy.deepcopy(cached[1])
            result["meta"]["cache_hit"] = True
            return result

        with self._lock:
            cached = self._cache.get(selected)
            if cached and not force and time.time() - cached[0] < CACHE_SECONDS:
                result = copy.deepcopy(cached[1])
                result["meta"]["cache_hit"] = True
                return result
            runner = WarehouseAttributionRunner(
                config=self.config,
                table=self.table_name,
                partition=selected,
                query_rows=self._run_sql_rows,
            )
            result = runner.run()
            result["meta"]["cache_hit"] = False
            self._cache[selected] = (time.time(), result)
            return copy.deepcopy(result)

    def path_trend(self, record_id: str, partition: str | None = None) -> dict[str, Any]:
        """Load only the selected server-side alert path's 15-day daily series."""
        if not SAFE_RECORD_ID.fullmatch(record_id):
            raise AttributionServiceError("预警路径标识格式不合法。")

        dashboard = self.dashboard(partition=partition)
        selected_partition = dashboard["meta"]["partition"]
        record = next((item for item in dashboard["merged_alerts"] if item["id"] == record_id), None)
        if record is None:
            raise AttributionServiceError("未在当前合并预警结果中找到该路径，请刷新归因结果后重试。")

        cache_key = (selected_partition, record_id)
        cached = self._path_trend_cache.get(cache_key)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return copy.deepcopy(cached[1])

        runner = WarehouseAttributionRunner(
            config=self.config,
            table=self.table_name,
            partition=selected_partition,
            query_rows=self._run_sql_rows,
        )
        result = runner.path_trend(record, dashboard["daily_trend"])
        self._path_trend_cache[cache_key] = (time.time(), result)
        return copy.deepcopy(result)


load_local_env()
service = AttributionService()
app = FastAPI(title="Risk BI · Credit Attribution API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AttributionServiceError):
        return HTTPException(status_code=503, detail=str(exc))
    # Avoid leaking SQL text, endpoint details, or credentials to the browser.
    return HTTPException(status_code=502, detail="MaxCompute 数据读取失败，请检查服务端连接与表权限。")


@app.get("/api/credit-attribution/health")
def health() -> dict[str, Any]:
    try:
        connection = get_connection()
        return {
            "status": "configured",
            "project": connection.project,
            "table": service.table_name,
            "credential_source": "environment" if os.getenv("MAXCOMPUTE_ACCESS_KEY_ID") else "notebook",
        }
    except AttributionServiceError as exc:
        return {"status": "not_configured", "detail": str(exc)}


@app.get("/api/credit-attribution/partitions")
def partitions() -> JSONResponse:
    try:
        return JSONResponse(content={"partitions": service.available_partitions()})
    except Exception as exc:
        raise handle_error(exc) from exc


@app.get("/api/credit-attribution/dashboard")
def dashboard(
    pt: str | None = Query(default=None, max_length=64),
    force: bool = Query(default=False),
) -> JSONResponse:
    try:
        return JSONResponse(content=json_safe(service.dashboard(partition=pt, force=force)))
    except Exception as exc:
        raise handle_error(exc) from exc


@app.get("/api/credit-attribution/path-trend")
def path_trend(
    record_id: str = Query(min_length=12, max_length=12),
    pt: str | None = Query(default=None, max_length=64),
) -> JSONResponse:
    try:
        return JSONResponse(content=json_safe(service.path_trend(record_id=record_id, partition=pt)))
    except Exception as exc:
        raise handle_error(exc) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=int(os.getenv("ATTRIBUTION_API_PORT", "8010")), reload=False)
