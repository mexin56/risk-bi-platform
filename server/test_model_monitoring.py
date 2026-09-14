from server.model_monitoring import (
    MODEL_SCORES,
    build_business_type_metrics,
    build_daily_trend,
    build_monitoring_payload,
    build_model_effect_trend,
    build_model_effect_weekly,
    build_score_band_metrics,
    build_stage_metrics,
)


def test_stage_metrics_expose_rates_with_their_denominators():
    result = build_stage_metrics(
        {
            "row_count": "100",
            "approval_labeled_cnt": "90",
            "approval_pass_cnt": "45",
            "loan_labeled_cnt": "100",
            "loan_success_cnt": "60",
            "repayment_labeled_cnt": "60",
            "fpd7_base": "40",
            "fpd7_bad": "8",
            "fpd30_base": "20",
            "fpd30_bad": "4",
            "term3_base": "10",
            "term3_bad": "5",
        }
    )

    by_key = {item["key"]: item for item in result}
    assert by_key["approval_pass_rate"]["rate"] == 0.5
    assert by_key["approval_pass_rate"]["denominator"] == 90
    assert by_key["loan_success_rate"]["rate"] == 0.6
    assert by_key["fpd7_rate"]["rate"] == 0.2
    assert by_key["fpd7_rate"]["numerator"] == 8
    assert by_key["fpd7_rate"]["denominator"] == 40


def test_daily_trend_marks_recent_performance_as_immature():
    result = build_daily_trend(
        [
            {
                "day": "2026-09-01",
                "applications": "100",
                "approved": "50",
                "loan_success": "70",
                "fpd7_base": "10",
                "fpd7_bad": "2",
                "fpd30_base": "5",
                "fpd30_bad": "1",
            },
            {
                "day": "2026-08-01",
                "applications": "100",
                "approved": "50",
                "loan_success": "70",
                "fpd7_base": "60",
                "fpd7_bad": "12",
                "fpd30_base": "40",
                "fpd30_bad": "8",
            },
        ]
    )

    by_day = {item["day"]: item for item in result}
    assert by_day["2026-09-01"]["fpd7_rate"] is None
    assert by_day["2026-09-01"]["fpd7_observation_ratio"] == 10 / 70
    assert by_day["2026-09-01"]["maturity_warning"] is True
    assert by_day["2026-08-01"]["fpd7_rate"] == 0.2
    assert by_day["2026-08-01"]["fpd30_rate"] == 0.2
    assert by_day["2026-08-01"]["maturity_warning"] is False


def test_business_type_and_score_band_metrics_calculate_bad_rates():
    business = build_business_type_metrics(
        [
            {"business_type": "PDL", "applications": "10", "loan_success": "8", "fpd7_base": "5", "fpd7_bad": "1", "fpd30_base": "4", "fpd30_bad": "1"},
            {"business_type": None, "applications": "2", "loan_success": "0", "fpd7_base": "0", "fpd7_bad": "0", "fpd30_base": "0", "fpd30_bad": "0"},
        ]
    )
    assert business[0]["business_type"] == "PDL"
    assert business[0]["fpd7_rate"] == 0.2
    assert business[1]["business_type"] == "未知"
    assert business[1]["fpd7_rate"] is None

    bands = build_score_band_metrics(
        [
            {"band_order": "1", "band": "0-99", "samples": "20", "fpd7_base": "10", "fpd7_bad": "4", "fpd30_base": "8", "fpd30_bad": "2"},
            {"band_order": "0", "band": "未命中/-1", "samples": "2", "fpd7_base": "0", "fpd7_bad": "0", "fpd30_base": "0", "fpd30_bad": "0"},
        ]
    )
    assert [row["band"] for row in bands] == ["未命中/-1", "0-99"]
    assert bands[1]["fpd7_rate"] == 0.4


def test_model_effect_trend_calculates_direction_agnostic_auc_and_ks():
    result = build_model_effect_trend(
        [
            {"day": "2026-09-01", "model": "op_v2_score", "score_bin": 0, "score_valid_cnt": 2000, "fpd7_base": 1000, "fpd7_bad": 800},
            {"day": "2026-09-01", "model": "op_v2_score", "score_bin": 1, "score_valid_cnt": 2000, "fpd7_base": 1000, "fpd7_bad": 200},
        ],
        [{"day": "2026-09-01", "applications": 5000, "loan_success": 4000}],
    )

    assert result[0]["auc"] == 0.8
    assert result[0]["ks"] == 0.6
    assert result[0]["score_coverage"] == 0.8
    assert result[0]["target"] == "fpd7"


def test_model_effect_trend_reverses_score_direction_without_changing_effect():
    result = build_model_effect_trend(
        [
            {"day": "2026-09-01", "model": "m", "score_bin": 0, "score_valid_cnt": 2000, "fpd7_base": 1000, "fpd7_bad": 200},
            {"day": "2026-09-01", "model": "m", "score_bin": 1, "score_valid_cnt": 2000, "fpd7_base": 1000, "fpd7_bad": 800},
        ],
        [{"day": "2026-09-01", "applications": 4000, "loan_success": 4000}],
    )

    assert result[0]["auc"] == 0.8
    assert result[0]["ks"] == 0.6


def test_model_effect_trend_blanks_immature_dates_instead_of_zero():
    result = build_model_effect_trend(
        [{"day": "2026-09-01", "model": "m", "score_bin": 0, "score_valid_cnt": 2000, "fpd7_base": 1000, "fpd7_bad": 400}],
        [{"day": "2026-09-01", "applications": 10000, "loan_success": 10000}],
    )

    assert result[0]["maturity_warning"] is True
    assert result[0]["auc"] is None
    assert result[0]["ks"] is None


def test_model_effect_weekly_groups_scores_by_alias_and_recomputes_metrics():
    result = build_model_effect_weekly(
        [
            {
                "day": "2026-09-07",
                "alias": "CASHSHX",
                "model": "op_v2_score",
                "score_bin": 0,
                "score_valid_cnt": 500,
                "fpd7_base": 500,
                "fpd7_bad": 400,
            },
            {
                "day": "2026-09-08",
                "alias": "CASHSHX",
                "model": "op_v2_score",
                "score_bin": 1,
                "score_valid_cnt": 500,
                "fpd7_base": 500,
                "fpd7_bad": 100,
            },
            {
                "day": "2026-09-07",
                "alias": "CASHBO",
                "model": "op_v2_score",
                "score_bin": 0,
                "score_valid_cnt": 500,
                "fpd7_base": 500,
                "fpd7_bad": 100,
            },
            {
                "day": "2026-09-08",
                "alias": "CASHBO",
                "model": "op_v2_score",
                "score_bin": 1,
                "score_valid_cnt": 500,
                "fpd7_base": 500,
                "fpd7_bad": 400,
            },
        ],
        [
            {"day": "2026-09-07", "alias": "CASHSHX", "loan_success": 1000},
            {"day": "2026-09-08", "alias": "CASHSHX", "loan_success": 1000},
            {"day": "2026-09-07", "alias": "CASHBO", "loan_success": 1000},
            {"day": "2026-09-08", "alias": "CASHBO", "loan_success": 1000},
        ],
        target="fpd7",
    )

    by_alias = {row["alias"]: row for row in result}
    cashshx = by_alias["CASHSHX"]
    assert cashshx["week_start"] == "2026-09-07"
    assert cashshx["week_end"] == "2026-09-13"
    assert cashshx["count"] == 1000
    assert cashshx["badrate"] == 0.5
    assert cashshx["auc"] == 0.8
    assert cashshx["ks"] == 0.6
    assert cashshx["maturity_warning"] is False
    assert by_alias["CASHBO"]["auc"] == 0.8


def test_model_effect_weekly_merges_the_same_score_bin_across_days():
    result = build_model_effect_weekly(
        [
            {"day": "2026-09-07", "alias": "CASHSHX", "model": "m", "score_bin": 0, "fpd7_base": 100, "fpd7_bad": 80},
            {"day": "2026-09-08", "alias": "CASHSHX", "model": "m", "score_bin": 0, "fpd7_base": 100, "fpd7_bad": 60},
            {"day": "2026-09-07", "alias": "CASHSHX", "model": "m", "score_bin": 1, "fpd7_base": 100, "fpd7_bad": 20},
            {"day": "2026-09-08", "alias": "CASHSHX", "model": "m", "score_bin": 1, "fpd7_base": 100, "fpd7_bad": 0},
        ],
        [
            {"day": "2026-09-07", "alias": "CASHSHX", "loan_success": 200},
            {"day": "2026-09-08", "alias": "CASHSHX", "loan_success": 200},
        ],
        target="fpd7",
    )

    assert result[0]["auc"] == 0.8125
    assert result[0]["ks"] == 0.625


def test_model_effect_weekly_hides_all_display_metrics_below_mature_sample_threshold():
    result = build_model_effect_weekly(
        [
            {
                "day": "2026-08-31",
                "alias": "CASHSHX",
                "model": "ng_cashjq_new_score",
                "score_bin": 0,
                "score_valid_cnt": 50,
                "fpd1_base": 50,
                "fpd1_bad": 20,
            },
            {
                "day": "2026-09-01",
                "alias": "CASHSHX",
                "model": "ng_cashjq_new_score",
                "score_bin": 1,
                "score_valid_cnt": 49,
                "fpd1_base": 49,
                "fpd1_bad": 10,
            },
        ],
        [{"day": "2026-08-31", "alias": "CASHSHX", "applications": 200, "loan_success": 100}],
        target="fpd1",
    )

    assert len(result) == 1
    assert result[0]["mature_count"] == 99
    assert result[0]["maturity_warning"] is True
    assert result[0]["count"] is None
    assert result[0]["badrate"] is None
    assert result[0]["auc"] is None
    assert result[0]["ks"] is None


def test_model_effect_weekly_keeps_display_metrics_at_the_100_sample_boundary():
    result = build_model_effect_weekly(
        [{"day": "2026-08-31", "alias": "CASHSHX", "model": "m", "score_bin": 0, "score_valid_cnt": 100, "fpd1_base": 100, "fpd1_bad": 10}],
        [{"day": "2026-08-31", "alias": "CASHSHX", "applications": 100, "loan_success": 100}],
        target="fpd1",
    )

    assert result[0]["count"] == 100
    assert result[0]["badrate"] == 0.1


def test_model_effect_weekly_keeps_metrics_when_only_population_ratio_is_low():
    result = build_model_effect_weekly(
        [{"day": "2026-08-31", "alias": "CASHSHX", "model": "m", "score_bin": 0, "score_valid_cnt": 100, "fpd7_base": 100, "fpd7_bad": 10}],
        [{"day": "2026-08-31", "alias": "CASHSHX", "applications": 1000, "loan_success": 1000}],
        target="fpd7",
    )

    assert result[0]["maturity_warning"] is False
    assert result[0]["count"] == 100
    assert result[0]["badrate"] == 0.1
    assert result[0]["auc"] == 0.5
    assert result[0]["ks"] == 0.0


def test_model_scores_include_the_new_cashjq_score_fields():
    fields = {field for field, _label in MODEL_SCORES}
    assert {
        "ng_cashjq_utilization_high_v1_score",
        "ng_cashjq_loancnt_1_4_v1_score",
        "ng_cashjq_loancnt_1plus_v1_score",
    } <= fields


def test_monitoring_payload_contains_all_target_trends_and_latest_rows():
    payload = build_monitoring_payload(
        overview={"row_count": 4000},
        business_rows=[],
        daily_rows=[{"day": "2026-09-01", "applications": 4000, "loan_success": 4000}],
        score_band_rows=[],
        model_effect_rows=[
            {"day": "2026-09-01", "model": "m", "score_bin": 0, "score_valid_cnt": 2000, "fpd7_base": 1000, "fpd7_bad": 800, "fpd30_base": 1000, "fpd30_bad": 700, "term3_base": 1000, "term3_bad": 600},
            {"day": "2026-09-01", "model": "m", "score_bin": 1, "score_valid_cnt": 2000, "fpd7_base": 1000, "fpd7_bad": 200, "fpd30_base": 1000, "fpd30_bad": 300, "term3_base": 1000, "term3_bad": 400},
        ],
        partition="20260910",
        table_name="pb_biz_credit.ng_cash_model_monitoring_df",
    )

    assert {row["target"] for row in payload["model_effect_trend"]} == {"fpd1", "fpd7", "fpd10", "fpd15", "fpd30", "term3"}
    assert {row["target"] for row in payload["model_effect_weekly"]} == {"fpd1", "fpd7", "fpd10", "fpd15", "fpd30", "term3"}
    assert payload["model_effect_aliases"] == ["未知"]
    assert len(payload["latest_model_effect"]) == 6
    assert payload["latest_model_effect"][0]["model"] == "m"


def test_monitoring_payload_keeps_aliases_without_model_scores_in_filter_options():
    payload = build_monitoring_payload(
        overview={"row_count": 10},
        business_rows=[],
        daily_rows=[],
        score_band_rows=[],
        alias_daily_rows=[{"day": "2026-09-07", "alias": "CASHSHX", "applications": 10, "loan_success": 10}],
        partition="20260910",
        table_name="pb_biz_credit.ng_cash_model_monitoring_df",
    )

    assert payload["model_effect_aliases"] == ["CASHSHX"]


def test_monitoring_payload_exposes_model_monitoring_label_options():
    payload = build_monitoring_payload(
        overview={"row_count": 10},
        business_rows=[],
        daily_rows=[],
        score_band_rows=[],
        alias_daily_rows=[
            {"day": "2026-09-07", "alias": "CASHSHX", "flag_mob_type": "老客", "flag_product": "PDL_old", "cash_ser_call_node": "node_a", "applications": 5, "loan_success": 5},
            {"day": "2026-09-08", "alias": "CASHSHX", "flag_mob_type": "新客", "flag_product": "PDL_new", "cash_ser_call_node": "node_b", "applications": 5, "loan_success": 5},
        ],
        partition="20260913",
        table_name="pb_biz_credit.ng_cash_model_monitoring_df",
    )

    assert payload["model_effect_mob_types"] == ["新客", "老客"]
    assert payload["model_effect_products"] == ["PDL_new", "PDL_old"]
    assert payload["model_effect_cash_ser_call_nodes"] == ["INSTALLMENT_LOAN", "INSTANT_LOAN", "PALMPAY_LOAN"]


def test_model_effect_weekly_sums_label_slices_for_the_same_alias():
    result = build_model_effect_weekly(
        [
            {"day": "2026-08-31", "alias": "CASHSHX", "model": "m", "score_bin": 0, "score_valid_cnt": 100, "fpd7_base": 100, "fpd7_bad": 20},
        ],
        [
            {"day": "2026-08-31", "alias": "CASHSHX", "flag_mob_type": "老客", "applications": 100, "loan_success": 100},
            {"day": "2026-08-31", "alias": "CASHSHX", "flag_mob_type": "新客", "applications": 200, "loan_success": 200},
        ],
        target="fpd7",
    )

    assert result[0]["score_coverage"] == 100 / 300


def test_model_effect_weekly_uses_shared_target_population_for_sample_stats():
    result = build_model_effect_weekly(
        [
            {"day": "2026-08-24", "alias": "CASHJQ", "model": "m1", "score_bin": 0, "score_valid_cnt": 80, "fpd7_base": 80, "fpd7_bad": 8},
            {"day": "2026-08-24", "alias": "CASHJQ", "model": "m2", "score_bin": 0, "score_valid_cnt": 60, "fpd7_base": 60, "fpd7_bad": 6},
        ],
        [
            {"day": "2026-08-24", "alias": "CASHJQ", "applications": 500, "loan_success": 400, "fpd7_base": 300, "fpd7_bad": 30},
        ],
        target="fpd7",
    )

    assert {row["count"] for row in result} == {300}
    assert {row["badrate"] for row in result} == {0.1}


def test_model_effect_weekly_uses_available_fpd7_effect_when_population_ratio_is_below_half():
    result = build_model_effect_weekly(
        [
            {"day": "2026-08-24", "alias": "CASHJQ", "model": "m", "score_bin": 0, "score_valid_cnt": 100, "fpd7_base": 100, "fpd7_bad": 80},
            {"day": "2026-08-24", "alias": "CASHJQ", "model": "m", "score_bin": 1, "score_valid_cnt": 100, "fpd7_base": 100, "fpd7_bad": 20},
        ],
        [
            {"day": "2026-08-24", "alias": "CASHJQ", "applications": 1000, "loan_success": 1000, "fpd7_base": 200, "fpd7_bad": 100},
        ],
        target="fpd7",
    )

    assert result[0]["count"] == 200
    assert result[0]["badrate"] == 0.5
    assert result[0]["maturity_ratio"] == 0.2
    assert result[0]["maturity_warning"] is False
    assert result[0]["auc"] == 0.8
    assert result[0]["ks"] == 0.6
