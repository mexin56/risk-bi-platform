"""授信归因预计算管线(P1:存储层 + serving 快照;P2 接入 Dagster 调度)。

用法(在 server/ 目录下):
    python -m pipeline.cli run --pt 20260822          # 计算并发布单个分区
    python -m pipeline.cli run --backfill 5           # 回填最近 5 个分区
    python -m pipeline.cli ingest --input result.json # 在线兜底结果写回发布
"""

from __future__ import annotations

from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SERVER_DIR / "data"
DB_PATH = DATA_DIR / "attribution.duckdb"      # 仅 pipeline 进程读写
SERVING_DIR = DATA_DIR / "serving"             # FastAPI 只读这一层
