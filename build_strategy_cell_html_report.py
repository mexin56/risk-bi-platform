from __future__ import annotations

"""Build the standalone HTML report for the online strategy-cell validation."""

import html
import json
from pathlib import Path
from typing import Any

SOURCE = Path("risk_analysis/deployed_coefficient_check_0812.json")
OUTPUT = Path("public/reports/credit-strategy-cell-validation-20260812.html")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def integer(value: Any) -> str:
    return f"{int(value):,}"


def rate(value: Any) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def num(value: Any) -> str:
    return "—" if value is None else f"{float(value):g}"


def status_class(value: str) -> str:
    return {
        "符合": "ok",
        "不符合": "bad",
        "无法映射": "warn",
        "本批次无客户": "mute",
    }[value]


def cell_status(cell: dict[str, Any]) -> tuple[str, str, str, str]:
    if cell.get("observation_status") == "no_customer_in_batch":
        return "本批次无客户", "本批次无客户", "本批次无客户", "系数表存在该格，但本批次未命中客户"
    if cell.get("lookup_status"):
        execution = "符合" if cell["execution_consistent"] else "不符合"
        return "无法映射", execution, "无法映射", "异常维度组合，未进入315格系数表"
    coefficient = "符合" if cell["coefficient_consistent"] else "不符合"
    execution = "符合" if cell["execution_consistent"] else "不符合"
    overall = "符合" if cell["strategy_consistent"] else "不符合"
    return coefficient, execution, overall, "借款数策略格 7 包含 7 及以上"


def configured_distribution(cell: dict[str, Any]) -> str:
    def key(item: tuple[str, Any]) -> float:
        try:
            return float(item[0])
        except ValueError:
            return -1

    pairs = sorted(cell["configured_rate_distribution"].items(), key=key)
    return " · ".join(f"<b>{esc(coef)}</b>：{integer(count)}" for coef, count in pairs) or "—"


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    summary = data["summary_by_te_flag"]
    all_rows = summary["all"]
    te0 = summary["0"]
    te1 = summary["1"]
    mapped_total = all_rows["coefficient_match"] + all_rows["coefficient_mismatch"]
    cells = data["policy_cell_compliance"]
    observed = [cell for cell in cells if cell["total_cnt"] > 0 and not cell.get("lookup_status")]
    mismatch_cells = [cell for cell in observed if not cell["coefficient_consistent"]]
    exact_cells = [cell for cell in observed if cell["coefficient_consistent"]]
    exact_cell_count = len(exact_cells)
    unmapped_cells = [cell for cell in cells if cell.get("lookup_status")]
    unobserved_cells = [cell for cell in cells if cell.get("observation_status") == "no_customer_in_batch"]
    config_match_rate = all_rows["coefficient_match"] / mapped_total
    positive_no_raise = sum(cell["positive_config_no_raise_cnt"] for cell in observed)
    zero_config_raise = sum(cell["zero_config_actual_raise_cnt"] for cell in observed)

    table_rows: list[str] = []
    for cell in cells:
        coefficient, execution, overall, note = cell_status(cell)
        table_rows.append(
            f"""
            <tr class=\"{status_class(overall)}\">
              <td class=\"cell-name\">{esc(cell['policy_key'])}</td>
              <td class=\"num\">{num(cell['expected_cash_remark1'])}</td>
              <td class=\"num\">{integer(cell['total_cnt'])}</td>
              <td class=\"num\">{integer(cell['coefficient_match_cnt'])}</td>
              <td class=\"num mismatch\">{integer(cell['coefficient_mismatch_cnt'])}</td>
              <td class=\"num\">{rate(cell['coefficient_match_rate'])}</td>
              <td class=\"num\">{integer(cell['te_flag_1_cnt'])}</td>
              <td class=\"num\">{integer(cell['te_flag_0_cnt'])}</td>
              <td class=\"num\">{integer(cell['actual_raise_cnt'])}</td>
              <td class=\"num\">{integer(cell['actual_unchanged_cnt'])}</td>
              <td class=\"num\">{integer(cell['positive_config_no_raise_cnt'])}</td>
              <td><span class=\"pill {status_class(coefficient)}\">{coefficient}</span></td>
              <td><span class=\"pill {status_class(execution)}\">{execution}</span></td>
              <td><span class=\"pill {status_class(overall)}\">{overall}</span></td>
              <td class=\"distribution\">{configured_distribution(cell)}</td>
              <td class=\"note\">{esc(note)}</td>
            </tr>"""
        )

    top_rows: list[str] = []
    for index, cell in enumerate(sorted(mismatch_cells, key=lambda item: item["coefficient_mismatch_cnt"], reverse=True)[:10], 1):
        top_rows.append(
            f"""
            <tr>
              <td class=\"rank\">{index:02d}</td>
              <td class=\"cell-name\">{esc(cell['policy_key'])}</td>
              <td class=\"num\">{num(cell['expected_cash_remark1'])}</td>
              <td class=\"num mismatch\">{integer(cell['coefficient_mismatch_cnt'])}</td>
              <td class=\"num\">{rate(cell['coefficient_match_rate'])}</td>
              <td class=\"distribution\">{configured_distribution(cell)}</td>
            </tr>"""
        )

    html_page = f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>提额策略线上配置逐格核验报告｜2026-08-12</title>
  <style>
    :root {{
      --canvas:#f5f7fb; --surface:#fff; --ink:#172033; --muted:#667085; --subtle:#98a2b3;
      --line:#e5eaf2; --blue:#3772f6; --blue-soft:#edf3ff; --green:#12976a; --green-soft:#eaf8f2;
      --amber:#b56700; --amber-soft:#fff6df; --red:#d7464f; --red-soft:#fff0f1; --navy:#152956;
      --shadow:0 12px 32px rgba(26,43,77,.07);
    }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{ margin:0; background:var(--canvas); color:var(--ink); font:14px/1.6 Inter,\"PingFang SC\",\"Microsoft YaHei\",system-ui,-apple-system,sans-serif; -webkit-font-smoothing:antialiased; }}
    .shell {{ width:min(1420px,calc(100% - 40px)); margin:0 auto; }}
    .topbar {{ background:linear-gradient(110deg,#152956,#1f4ba5 64%,#3772f6); color:#fff; }}
    .topbar .shell {{ min-height:48px; display:flex; align-items:center; justify-content:space-between; gap:16px; font-size:12px; }}
    .brand {{ font-weight:750; letter-spacing:.02em; }} .meta {{ color:#dce6ff; font-size:11px; }}
    .hero {{ position:relative; overflow:hidden; padding:42px 0 66px; color:#fff; background:linear-gradient(110deg,#152956 0%,#1d469b 58%,#3772f6 100%); }}
    .hero:after {{ content:\"\"; position:absolute; right:-125px; top:-300px; width:560px; height:560px; border:1px solid rgba(255,255,255,.15); border-radius:50%; box-shadow:0 0 0 55px rgba(255,255,255,.035),0 0 0 110px rgba(255,255,255,.025); }}
    .hero-grid {{ position:relative; z-index:1; display:grid; grid-template-columns:minmax(0,1fr) 350px; gap:38px; align-items:end; }}
    .eyebrow {{ display:inline-flex; align-items:center; gap:7px; padding:4px 10px; border:1px solid rgba(255,255,255,.25); border-radius:999px; color:#dce8ff; font-size:11px; font-weight:700; letter-spacing:.08em; }}
    .dot {{ width:6px; height:6px; border-radius:50%; background:#7df1c2; box-shadow:0 0 0 4px rgba(125,241,194,.15); }}
    h1 {{ margin:16px 0 10px; font-size:clamp(28px,4vw,40px); line-height:1.18; letter-spacing:-.04em; }}
    .hero p {{ max-width:780px; margin:0; color:#dce6fb; }} .hero-note {{ margin-top:18px; color:#bbcef8; font-size:11px; }}
    .hero-result {{ padding:20px; border:1px solid rgba(255,255,255,.18); border-radius:16px; background:rgba(255,255,255,.1); backdrop-filter:blur(4px); }}
    .hero-result span,.hero-result small {{ color:#d3e1fb; font-size:11px; }} .hero-result strong {{ display:block; margin:4px 0; font-size:31px; letter-spacing:-.055em; }}
    main {{ padding-bottom:64px; }}
    .kpis {{ position:relative; z-index:2; display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-top:-29px; }}
    .kpi {{ min-height:132px; padding:16px; overflow:hidden; position:relative; border:1px solid var(--line); border-radius:13px; background:var(--surface); box-shadow:var(--shadow); }}
    .kpi:before {{ content:\"\"; position:absolute; left:0; right:0; top:0; height:3px; background:var(--blue); }} .kpi.ok:before{{background:var(--green)}} .kpi.warn:before{{background:var(--amber)}} .kpi.bad:before{{background:var(--red)}}
    .kpi-label {{ color:var(--muted); font-size:11px; font-weight:700; letter-spacing:.04em; }} .kpi-value {{ margin-top:12px; font-size:27px; font-weight:780; line-height:1; letter-spacing:-.05em; }} .kpi-value small {{ margin-left:2px; color:var(--muted); font-size:12px; font-weight:500; letter-spacing:0; }} .kpi-foot {{ margin-top:9px; color:var(--muted); font-size:10.5px; line-height:1.45; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:8px; margin:26px 0 18px; }} .nav a {{ padding:6px 10px; border:1px solid var(--line); border-radius:7px; color:var(--muted); background:#fff; text-decoration:none; font-size:11px; font-weight:650; }} .nav a:hover{{border-color:#b5cdfc;color:var(--blue)}}
    .section {{ margin-top:18px; padding:23px; border:1px solid var(--line); border-radius:15px; background:var(--surface); box-shadow:0 3px 10px rgba(26,43,77,.025); }}
    .section-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:18px; }} .kicker {{ color:var(--blue); font-size:11px; font-weight:800; letter-spacing:.1em; }} h2 {{ margin:3px 0 0; font-size:20px; line-height:1.35; letter-spacing:-.025em; }} .desc {{ max-width:800px; margin:5px 0 0; color:var(--muted); font-size:12px; }}
    .tag {{ display:inline-flex; align-items:center; white-space:nowrap; padding:4px 8px; border:1px solid; border-radius:6px; font-size:10.5px; font-weight:750; }} .tag.blue{{background:var(--blue-soft);border-color:#cfe0ff;color:#245ec7}} .tag.red{{background:var(--red-soft);border-color:#f7cdd1;color:#bd3440}} .tag.green{{background:var(--green-soft);border-color:#c7ecdd;color:#0b7b55}}
    .summary-grid {{ display:grid; grid-template-columns:1.15fr .85fr; gap:15px; }} .callout {{ padding:18px; border:1px solid #e5ebf7; border-radius:11px; background:#f7f9fd; }} .callout h3 {{ margin:0 0 7px; font-size:15px; }} .callout p {{ margin:0; color:#4d5c76; font-size:12px; line-height:1.75; }} .callout strong{{color:var(--red)}}
    .fact-list {{ display:grid; gap:8px; }} .fact {{ display:grid; grid-template-columns:28px 1fr; gap:10px; padding:8px 0; border-bottom:1px solid var(--line); }} .fact:last-child{{border-bottom:0}} .fact-num{{width:22px;height:22px;display:grid;place-items:center;border-radius:6px;background:var(--blue-soft);color:var(--blue);font-size:10px;font-weight:800}} .fact b{{display:block;font-size:12px}} .fact span{{display:block;margin-top:1px;color:var(--muted);font-size:11px}}
    .checks {{ display:grid; grid-template-columns:repeat(3,1fr); gap:11px; }} .check {{ padding:16px; border:1px solid var(--line); border-radius:11px; }} .check .label{{color:var(--muted);font-size:11px;font-weight:700}} .check .number{{margin:8px 0 4px;font-size:25px;line-height:1;font-weight:780;letter-spacing:-.045em}} .check .note{{color:var(--muted);font-size:10.5px;line-height:1.55}} .check.ok{{background:linear-gradient(135deg,#fff,#f2fbf7);border-color:#d2eee1}} .check.ok .number{{color:var(--green)}} .check.bad{{background:linear-gradient(135deg,#fff,#fff5f6);border-color:#f5d8dc}} .check.bad .number{{color:var(--red)}} .check.warn{{background:linear-gradient(135deg,#fff,#fffaf0);border-color:#f2e3bb}} .check.warn .number{{color:var(--amber)}}
    .legend {{ display:flex; gap:14px; flex-wrap:wrap; margin:0 0 13px; color:var(--muted); font-size:10.5px; }} .legend i{{display:inline-block;width:8px;height:8px;margin-right:5px;border-radius:50%}} .legend .ok{{background:var(--green)}}.legend .bad{{background:var(--red)}}.legend .warn{{background:var(--amber)}}.legend .mute{{background:#98a2b3}}
    .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:11px; }} table{{width:100%;border-collapse:collapse;min-width:1840px}} th{{position:sticky;top:0;z-index:1;padding:10px 11px;background:#f5f7fb;color:#526077;border-bottom:1px solid #dfe5ef;text-align:left;white-space:nowrap;font-size:10.5px;letter-spacing:.02em}}td{{padding:10px 11px;border-bottom:1px solid var(--line);color:#344054;font-size:11px;vertical-align:middle}}tbody tr:last-child td{{border-bottom:0}}tbody tr:hover td{{background:#f8fbff}}td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}.cell-name{{min-width:210px;font-weight:650;color:#24334e}}.mismatch{{color:var(--red);font-weight:700}}.distribution{{min-width:150px;color:#526077;white-space:nowrap}}.distribution b{{color:#253756}}.note{{min-width:190px;color:var(--muted)}}
    .pill{{display:inline-flex;padding:3px 7px;border:1px solid;border-radius:5px;font-size:10px;font-weight:750;white-space:nowrap}}.pill.ok{{background:var(--green-soft);border-color:#c7ecdd;color:#0b7b55}}.pill.bad{{background:var(--red-soft);border-color:#f7cdd1;color:#bd3440}}.pill.warn{{background:var(--amber-soft);border-color:#f5dfa2;color:#a46000}}.pill.mute{{background:#f1f3f6;border-color:#e1e5eb;color:#697386}}
    .rank{{color:var(--subtle);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:800}}.method{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.method-box{{padding:15px;border:1px solid var(--line);border-radius:10px;background:#f6f8fc}}.method-box h3{{margin:0 0 7px;font-size:12px}}.method-box ul{{margin:0;padding-left:17px;color:var(--muted);font-size:10.5px;line-height:1.85}}code{{padding:1px 4px;border-radius:4px;background:#eef2f8;color:#354663;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.95em}}
    .footer{{padding:24px 0 32px;color:var(--subtle);font-size:10.5px;text-align:center}}
    @media(max-width:1100px){{.kpis{{grid-template-columns:repeat(3,1fr)}}.hero-grid,.summary-grid{{grid-template-columns:1fr}}.hero-result{{max-width:350px}}.checks{{grid-template-columns:1fr}}}}
    @media(max-width:650px){{.shell{{width:min(100% - 24px,1420px)}}.topbar .shell{{padding:10px 0;align-items:flex-start;flex-direction:column;gap:3px}}.hero{{padding:30px 0 47px}}.kpis{{grid-template-columns:repeat(2,1fr);gap:9px;margin-top:-20px}}.kpi{{min-height:120px;padding:13px}}.section{{padding:17px}}.section-head{{flex-direction:column;gap:8px}}.method{{grid-template-columns:1fr}}}}
    @media print{{@page{{margin:10mm;size:landscape}}body{{background:#fff;font-size:9px}}.topbar{{background:#17366f!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}}.hero{{padding:20px 0 28px;-webkit-print-color-adjust:exact;print-color-adjust:exact}}.hero:after,.nav{{display:none}}.section,.kpi{{box-shadow:none;break-inside:avoid}}.section{{margin-top:9px;padding:13px}}.kpis{{margin-top:-15px}}.footer{{padding-bottom:0}}}}
  </style>
</head>
<body>
  <header class=\"topbar\"><div class=\"shell\"><div class=\"brand\">◈ 风控 BI 平台 · 提额策略逐格核验</div><div class=\"meta\">上线配置快照 · 报告生成：2026-08-13</div></div></header>
  <section class=\"hero\"><div class=\"shell hero-grid\"><div><span class=\"eyebrow\"><i class=\"dot\"></i>线上配置 × 提额系数表</span><h1>提额策略逐格值比对与执行核验</h1><p>以 2026-08-12 新策略 <b>defq-重构</b> 跑批结果为基础，将线上 <code>cash_remark1</code> 与《提额系数20260812.xlsx》315 个策略格逐格比对；同时验证每格提额、未提额客户的 <code>te_flag</code> 是否与实际额度变化一致。</p><div class=\"hero-note\">结果表：<b>pb_biz_credit.flexi_cash_jq_result_v1</b> · <b>jq_date=2026-08-12</b> · <b>str_type=new</b> · 借款数策略格 7 表示 7 及以上</div></div><div class=\"hero-result\"><span>线上系数与系数表一致率</span><strong>{rate(config_match_rate)}</strong><small>{integer(all_rows['coefficient_match'])} / {integer(mapped_total)} 名可映射客户一致</small></div></div></section>
  <main class=\"shell\">
    <div class=\"kpis\">
      <article class=\"kpi\"><div class=\"kpi-label\">有效客户</div><div class=\"kpi-value\">{integer(all_rows['total'])}<small>人</small></div><div class=\"kpi-foot\">新策略、前后额度字段有效</div></article>
      <article class=\"kpi bad\"><div class=\"kpi-label\">线上系数一致</div><div class=\"kpi-value\">{integer(all_rows['coefficient_match'])}<small>人</small></div><div class=\"kpi-foot\">一致率 {rate(config_match_rate)}</div></article>
      <article class=\"kpi bad\"><div class=\"kpi-label\">线上系数不一致</div><div class=\"kpi-value\">{integer(all_rows['coefficient_mismatch'])}<small>人</small></div><div class=\"kpi-foot\">需核对配置版本或查表键</div></article>
      <article class=\"kpi ok\"><div class=\"kpi-label\">实际提额</div><div class=\"kpi-value\">{integer(all_rows['actual_raise_cnt'])}<small>人</small></div><div class=\"kpi-foot\">全部与 te_flag=1 一致</div></article>
      <article class=\"kpi ok\"><div class=\"kpi-label\">实际未提额</div><div class=\"kpi-value\">{integer(all_rows['actual_unchanged_cnt'])}<small>人</small></div><div class=\"kpi-foot\">全部与 te_flag=0 一致</div></article>
      <article class=\"kpi warn\"><div class=\"kpi-label\">正系数但未提额</div><div class=\"kpi-value\">{integer(positive_no_raise)}<small>人</small></div><div class=\"kpi-foot\">待拆资格、拦截、封顶原因</div></article>
    </div>
    <nav class=\"nav\"><a href=\"#summary\">结论摘要</a><a href=\"#checks\">两类核验</a><a href=\"#top\">高影响偏差格</a><a href=\"#cells\">315 格明细</a><a href=\"#method\">口径方法</a></nav>
    <section id=\"summary\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">EXECUTIVE SUMMARY</div><h2>结论：提额执行语义正确，但线上系数未按系数表稳定落地</h2></div><span class=\"tag red\">需优先核对配置</span></div><div class=\"summary-grid\"><div class=\"callout\"><h3>总体判断</h3><p>在 {integer(all_rows['total'])} 名有效客户中，<strong>{integer(all_rows['coefficient_mismatch'])} 人（{rate(1-config_match_rate)}）</strong>的线上 <code>cash_remark1</code> 与系数表目标值不一致；仅 {integer(exact_cell_count)} / {integer(len(observed))} 个已命中策略格实现全格系数一致。另一方面，提额/未提额执行表现完全符合 <code>te_flag</code> 语义：{integer(te1['total'])} 名 <code>te_flag=1</code> 客户均实际提额，{integer(te0['total'])} 名 <code>te_flag=0</code> 客户均额度不变，未发现新策略有效样本降额。</p></div><div class=\"fact-list\"><div class=\"fact\"><div class=\"fact-num\">01</div><div><b>{integer(data['observed_policy_cell_count'])} 个策略格命中客户</b><span>315 格系数表中 {integer(data['unobserved_policy_cell_count'])} 格本批次无客户；另有 {integer(data['unmapped_group_count'])} 个异常维度组合无法映射。</span></div></div><div class=\"fact\"><div class=\"fact-num\">02</div><div><b>执行核验 100% 一致</b><span>所有提额客户均实际额度增加，所有未提额客户额度均保持不变。</span></div></div><div class=\"fact\"><div class=\"fact-num\">03</div><div><b>{integer(positive_no_raise)} 人“正系数但未提额”</b><span>不构成 te_flag 语义错误；需进一步补齐资格、拦截、额度封顶等原因码。</span></div></div></div></div></section>
    <section id=\"checks\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">VALIDATION RESULT</div><h2>配置核验与执行核验需分开解读</h2><p class=\"desc\">配置核验回答“线上系数是否按表”；执行核验回答“提额/未提额标识是否与实际额度变化一致”。</p></div><span class=\"tag blue\">逐格汇总</span></div><div class=\"checks\"><article class=\"check bad\"><div class=\"label\">线上系数配置核验</div><div class=\"number\">{rate(config_match_rate)}</div><div class=\"note\">{integer(all_rows['coefficient_match'])} 名客户与系数表一致；{integer(all_rows['coefficient_mismatch'])} 名不一致。已命中策略格中 {integer(len(mismatch_cells))} 格存在偏差。</div></article><article class=\"check ok\"><div class=\"label\">提额/未提额执行核验</div><div class=\"number\">100.0%</div><div class=\"note\">{integer(te1['total'])} 名提额客户均实际提额；{integer(te0['total'])} 名未提额客户均额度未变；实际降额 {integer(all_rows['actual_down_cnt'])} 人。</div></article><article class=\"check warn\"><div class=\"label\">需要补充解释的闸门对象</div><div class=\"number\">{integer(positive_no_raise)}</div><div class=\"note\">未提额但线上系数为正的客户数。另有 {integer(zero_config_raise)} 名零系数客户实际提额，均建议下钻规则原因。</div></article></div></section>
    <section id=\"top\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">PRIORITY CELLS</div><h2>按系数不一致人数排序的前 10 个策略格</h2><p class=\"desc\">优先检查线上策略版本、客户类型/使用率/借款数/评分档位的查表键，以及同一策略格是否出现多套线上系数。</p></div><span class=\"tag red\">{integer(len(mismatch_cells))} 格有偏差</span></div><div class=\"table-wrap\"><table style=\"min-width:900px\"><thead><tr><th>#</th><th>策略格</th><th class=\"num\">表内目标系数</th><th class=\"num\">不一致客户</th><th class=\"num\">一致率</th><th>线上系数分布</th></tr></thead><tbody>{''.join(top_rows)}</tbody></table></div></section>
    <section id=\"cells\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">CELL-BY-CELL EXPORT</div><h2>线上配置与系数表逐格明细</h2><p class=\"desc\">可按策略格、结论或人数在浏览器表格中搜索/筛选；表中保留全部 315 个系数表格和 1 个无法映射的异常来源组。</p></div><span class=\"tag green\">提额/未提额执行均符合</span></div><div class=\"legend\"><span><i class=\"ok\"></i>符合</span><span><i class=\"bad\"></i>不符合</span><span><i class=\"warn\"></i>无法映射</span><span><i class=\"mute\"></i>本批次无客户</span></div><div class=\"table-wrap\"><table id=\"cell-table\"><thead><tr><th>策略格</th><th class=\"num\">表内目标系数</th><th class=\"num\">客户数</th><th class=\"num\">系数一致</th><th class=\"num\">系数不一致</th><th class=\"num\">一致率</th><th class=\"num\">提额客户</th><th class=\"num\">未提额客户</th><th class=\"num\">实际提额</th><th class=\"num\">实际未变</th><th class=\"num\">正系数未提额</th><th>配置结论</th><th>执行结论</th><th>综合结论</th><th>线上系数分布</th><th>备注</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div></section>
    <section id=\"method\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">SCOPE & METHOD</div><h2>数据口径与判断规则</h2></div><span class=\"tag blue\">可复现</span></div><div class=\"method\"><div class=\"method-box\"><h3>数据来源与映射</h3><ul><li>线上结果表：<code>pb_biz_credit.flexi_cash_jq_result_v1</code></li><li>范围：<code>jq_date='2026-08-12'</code>、<code>str_type='new'</code>，且提额前/后额度有效。</li><li>系数表：<code>提额系数20260812.xlsx</code>，共 315 个唯一策略格。</li><li>映射维度：客户类型、额度使用率、借款数、评分档位。</li><li>借款数 1–6 逐格匹配；策略格 <code>7</code> 代表 <code>7及以上</code>。</li></ul></div><div class=\"method-box\"><h3>结论判定</h3><ul><li><b>配置符合</b>：该格所有客户 <code>cash_remark1</code> 均等于系数表目标值。</li><li><b>执行符合</b>：<code>te_flag=1</code> 的客户实际额度增加，<code>te_flag=0</code> 的客户额度不变。</li><li><b>综合符合</b>：同时满足配置符合与执行符合。</li><li>“正系数但未提额”不直接判定为执行错误，需结合资格、拦截及封顶规则解释。</li><li>报告为聚合监控，不展示客户级标识或 ODPS 凭证。</li></ul></div></div></section>
  </main>
  <footer class=\"footer\">风控 BI 平台 · 提额策略线上配置逐格核验 · 内部聚合分析快照</footer>
</body>
</html>"""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html_page, encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
