import json
from pathlib import Path

import app


def test_available_partitions_falls_back_to_local_serving_snapshots(monkeypatch, tmp_path: Path):
    serving_dir = tmp_path / "serving"
    serving_dir.mkdir()
    (serving_dir / "meta.json").write_text(
        json.dumps(
            {
                "snapshots": [
                    {"pt": "20260919", "offset": 0},
                    {"pt": "20260921", "offset": 0},
                    {"pt": "20260921", "offset": 45},
                ]
            }
        ),
        encoding="utf-8",
    )

    service = app.AttributionService.__new__(app.AttributionService)
    service._partition_cache = None
    monkeypatch.setattr(app, "SERVING_DIR", serving_dir)

    def maxcompute_is_unavailable():
        raise app.AttributionServiceError("MaxCompute unavailable")

    service._odps = maxcompute_is_unavailable

    assert service.available_partitions() == ["20260921", "20260919"]


def test_model_monitoring_partitions_falls_back_to_local_disk_cache(monkeypatch, tmp_path: Path):
    cache_dir = tmp_path / "model_monitoring_cache"
    cache_dir.mkdir()
    for partition in ("20260919", "20260921"):
        (cache_dir / f"pb_biz_credit.ng_cash_model_monitoring_df_{partition}____.json").write_text(
            json.dumps(
                {
                    "cache_key": f"pb_biz_credit.ng_cash_model_monitoring_df|{partition}||||",
                    "payload": {"model_coverage": []},
                }
            ),
            encoding="utf-8",
        )

    service = app.AttributionService.__new__(app.AttributionService)
    monkeypatch.setenv("MAXCOMPUTE_MODEL_MONITORING_TABLE", "pb_biz_credit.ng_cash_model_monitoring_df")
    monkeypatch.setattr(app, "MODEL_MONITOR_DISK_CACHE_DIR", cache_dir)

    def maxcompute_is_unavailable():
        raise app.AttributionServiceError("MaxCompute unavailable")

    service._odps = maxcompute_is_unavailable

    assert service.model_monitoring_partitions() == ["20260921", "20260919"]
