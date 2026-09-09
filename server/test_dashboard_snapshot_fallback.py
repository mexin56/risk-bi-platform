import threading
import time

import app


def test_dashboard_without_partition_uses_latest_serving_snapshot(monkeypatch):
    service = app.AttributionService.__new__(app.AttributionService)
    service.config = {"table": "pb_biz_credit.test_table"}
    service._cache = {}
    service._path_trend_cache = {}
    service._lock = threading.Lock()
    def maxcompute_partitions_must_not_run():
        raise AssertionError("首次打开页面不应查询 MaxCompute 分区元数据")

    service.available_partitions = maxcompute_partitions_must_not_run
    service._load_disk_cache = lambda _key: None
    service._save_disk_cache = lambda _key, _value: None
    service._enrich_approval = lambda _value, _partition, _offset: None

    snapshot = {
        "meta": {
            "generated_at": "2026-08-31T03:34:41+00:00",
            "partition": "20260829",
        },
        "merged_alerts": [],
    }

    class FakeServing:
        @staticmethod
        def read_dashboard_snapshot(_directory, partition, _offset):
            return snapshot if partition == "20260829" else None

    monkeypatch.setattr(app, "serving_assemble", FakeServing)

    class OnlineQueryMustNotRun:
        def __init__(self, **_kwargs):
            raise AssertionError("首次打开页面不应直接执行在线 MaxCompute 聚合")

    monkeypatch.setattr(app, "WarehouseAttributionRunner", OnlineQueryMustNotRun)

    result = service.dashboard()

    assert result["meta"]["partition"] == "20260829"
    assert result["meta"]["cache_hit"] is True


def test_dashboard_adopts_same_timestamp_serving_snapshot_after_async_ingest(monkeypatch):
    service = app.AttributionService.__new__(app.AttributionService)
    service.config = {"table": "pb_biz_credit.test_table"}
    service._cache = {
        "20260902|0": (
            time.time(),
            {"meta": {"partition": "20260902", "generated_at": "same", "serving": False}, "merged_alerts": []},
        )
    }
    service._path_trend_cache = {}
    service._lock = threading.Lock()
    service._load_disk_cache = lambda _key: None
    service._save_disk_cache = lambda _key, _value: None
    service._enrich_approval = lambda _value, _partition, _offset: None

    class FakeServing:
        @staticmethod
        def read_dashboard_snapshot(_directory, partition, _offset):
            if partition != "20260902":
                return None
            return {"meta": {"partition": partition, "generated_at": "same", "serving": True}, "merged_alerts": []}

    monkeypatch.setattr(app, "serving_assemble", FakeServing)

    result = service.dashboard(partition="20260902", force=False, offset=0)

    assert result["meta"]["serving"] is True


def test_force_compute_marks_async_refresh_when_path_snapshot_is_spawned(monkeypatch):
    service = app.AttributionService.__new__(app.AttributionService)
    service.config = {"table": "pb_biz_credit.test_table"}
    service._cache = {}
    service._path_trend_cache = {}
    service._lock = threading.Lock()
    service._save_disk_cache = lambda _key, _value: None
    service._enrich_approval = lambda _value, _partition, _offset: None
    spawned = []
    service._spawn_ingest = lambda partition, offset, _result: spawned.append((partition, offset))

    class FakeRunner:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            return {"meta": {"partition": "20260902", "generated_at": "new"}, "merged_alerts": []}

    monkeypatch.setattr(app, "WarehouseAttributionRunner", FakeRunner)

    result = service.dashboard(partition="20260902", force=True, offset=0)

    assert result["meta"]["async_refresh"] is True
    assert spawned == [("20260902", 0)]
