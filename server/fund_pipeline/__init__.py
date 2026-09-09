"""资金归结预计算管线：独立于授信归因的 DuckDB 与 serving 快照。"""

from __future__ import annotations

from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SERVER_DIR / "data"
DB_PATH = DATA_DIR / "fund_attribution.duckdb"
SERVING_DIR = DATA_DIR / "fund_serving"
