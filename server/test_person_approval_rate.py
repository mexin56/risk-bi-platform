import pandas as pd

from pipeline import assemble


def test_enrich_approval_rates_adds_person_rate_by_cid_sum():
    dashboard = {
        "merged_alerts": [
            {
                "id": "alert-1",
                "primary_window": "3d",
                "approval_rate_pct": None,
                "windows": {
                    "1d": {
                        "key": "1d",
                        "observation_start": "2026-08-30",
                        "observation_end": "2026-08-30",
                        "observation_count": 6,
                    },
                    "3d": {
                        "key": "3d",
                        "observation_start": "2026-08-28",
                        "observation_end": "2026-08-30",
                        "observation_count": 15,
                    },
                },
            }
        ],
        "suppressed_alerts": [],
    }
    frame = pd.DataFrame(
        [
            {"alert_id": "alert-1", "date": "2026-08-28", "approval_count": 1, "cid_cnt": 10, "approval_cid_cnt": 2},
            {"alert_id": "alert-1", "date": "2026-08-29", "approval_count": 2, "cid_cnt": 5, "approval_cid_cnt": 1},
            {"alert_id": "alert-1", "date": "2026-08-30", "approval_count": 3, "cid_cnt": 4, "approval_cid_cnt": 2},
        ]
    )
    frame["date"] = pd.to_datetime(frame["date"]).dt.date

    result = assemble.enrich_approval_rates(dashboard, frame)
    record = result["merged_alerts"][0]

    assert record["windows"]["1d"]["cid_cnt"] == 4.0
    assert record["windows"]["1d"]["approval_cid_cnt"] == 2.0
    assert record["windows"]["1d"]["cid_approval_rate_pct"] == 50.0
    assert record["windows"]["3d"]["cid_cnt"] == 19.0
    assert record["windows"]["3d"]["approval_cid_cnt"] == 5.0
    assert record["windows"]["3d"]["cid_approval_rate_pct"] == 5 / 19 * 100
    assert record["cid_approval_rate_pct"] == 5 / 19 * 100
