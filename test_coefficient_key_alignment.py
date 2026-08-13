from __future__ import annotations

"""Sanity test: can a simple field-code permutation explain rate mismatches?"""

import itertools
import json
from pathlib import Path

from analyze_deployed_coefficient import normalized_code, policy_lookup
from probe_flexi_cash_strategy import get_odps, query

TABLE = "pb_biz_credit.flexi_cash_jq_result_v1"
OUTPUT = Path("risk_analysis/coefficient_key_alignment_sanity.json")

CUSTOMER_CODES = ["HAVE_SINGLE_LOAN", "HAVE_SINGLE_NOLOAN", "NO_SINGLE"]
CUSTOMER_LABELS = ["\u6709\u5355\u671f\u501f\u6b3e", "\u65e0\u5355\u671f\u501f\u6b3e", "\u65e0\u5355\u671f"]
USE_CODES = ["1", "2", "3"]
USE_LABELS = ["\u9ad8\u989d\u5ea6\u4f7f\u7528\u7387", "\u4e2d\u989d\u5ea6\u4f7f\u7528\u7387", "\u4f4e\u989d\u5ea6\u4f7f\u7528\u7387"]
SCORE_CODES = ["1", "2", "3", "4", "5"]
SCORE_LABELS = ["E", "D", "C", "B", "A"]


def count_transform(value: object, kind: str) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    if kind == "same_clamp7":
        return max(1, min(number, 7))
    if kind == "minus1_clamp7":
        return max(1, min(number - 1, 7))
    if kind == "plus1_clamp7":
        return max(1, min(number + 1, 7))
    raise ValueError(kind)


def main() -> None:
    odps = get_odps()
    rows = query(
        odps,
        f"""
        SELECT jq_customer_flag, defq_use_rate_level, separate_installment_loan_cnt,
               jq_mix_score_bin, cash_remark1, te_flag, COUNT(1) AS cnt
        FROM {TABLE}
        WHERE jq_date='2026-08-12' AND str_type='new' AND te_flag=1
        GROUP BY jq_customer_flag, defq_use_rate_level, separate_installment_loan_cnt,
                 jq_mix_score_bin, cash_remark1, te_flag
        """,
    )
    policy = policy_lookup()
    trials = []
    for c_perm in itertools.permutations(CUSTOMER_LABELS):
        c_map = dict(zip(CUSTOMER_CODES, c_perm))
        for u_perm in itertools.permutations(USE_LABELS):
            u_map = dict(zip(USE_CODES, u_perm))
            for s_perm in itertools.permutations(SCORE_LABELS):
                s_map = dict(zip(SCORE_CODES, s_perm))
                for transform in ("same_clamp7", "minus1_clamp7", "plus1_clamp7"):
                    matched = 0
                    checked = 0
                    for row in rows:
                        customer = c_map.get(normalized_code(row["jq_customer_flag"]))
                        usage = u_map.get(normalized_code(row["defq_use_rate_level"]))
                        score = s_map.get(normalized_code(row["jq_mix_score_bin"]))
                        count = count_transform(row["separate_installment_loan_cnt"], transform)
                        if not customer or not usage or not score or count is None:
                            continue
                        expected = policy.get((customer, usage, count, score))
                        try:
                            actual = float(row["cash_remark1"])
                        except (TypeError, ValueError):
                            continue
                        checked += int(row["cnt"])
                        if expected is not None and abs(actual - expected) < 1e-10:
                            matched += int(row["cnt"])
                    trials.append({
                        "matched_cnt": matched,
                        "checked_cnt": checked,
                        "match_rate": matched / checked if checked else 0,
                        "customer_mapping": c_map,
                        "use_rate_mapping": u_map,
                        "score_mapping": s_map,
                        "loan_count_transform": transform,
                    })
    trials.sort(key=lambda item: item["matched_cnt"], reverse=True)
    original = next(
        item
        for item in trials
        if item["customer_mapping"] == dict(zip(CUSTOMER_CODES, CUSTOMER_LABELS))
        and item["use_rate_mapping"] == dict(zip(USE_CODES, USE_LABELS))
        and item["score_mapping"] == dict(zip(SCORE_CODES, SCORE_LABELS))
        and item["loan_count_transform"] == "same_clamp7"
    )
    output = {"original_dictionary_mapping": original, "top_10_alternative_code_mappings": trials[:10]}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
