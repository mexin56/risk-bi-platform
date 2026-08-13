from __future__ import annotations

"""Build a compact HTML report from the strategy-table execution workbook data."""

import html
import json
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

SOURCE = Path("risk_analysis/strategy_execution_by_cell_20260812.json")
WORKBOOK = Path("risk_analysis/提额策略执行分析_20260812_v2.xlsx")
OUTPUT = Path("public/reports/credit-strategy-execution-20260812.html")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def integer(value: Any) -> str:
    return f"{int(value or 0):,}"


def yuan(value: Any, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{digits}f}"


def pct(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def conclusion_class(value: str) -> str:
    if value == "系数与提额执行均符合":
        return "pass"
    if value == "提额执行符合；系数需核对":
        return "check"
    if value == "本批次无样本":
        return "empty"
    return "warn"


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    # Validate that the accompanying user-facing workbook is readable.
    workbook = load_workbook(WORKBOOK, read_only=True, data_only=True)
    if "整体达成" not in workbook.sheetnames:
        raise RuntimeError("Missing overall-attainment sheet in execution workbook")
    workbook.close()
    full = data["overall"]["full_valid"]
    mapped = data["overall"]["mapped_strategy_table"]
    unmapped = data["overall"]["unmapped"]
    rows = data["rows"]
    report_xlsx_name = "\u63d0\u989d\u7b56\u7565\u6267\u884c\u5206\u6790_20260812_v2.xlsx"
    coefficient_rate_key = "\u6ee1\u8db3\u63d0\u989d\u6761\u4ef6\u5ba2\u6237\u7ebf\u4e0a\u7cfb\u6570\u4e00\u81f4\u7387"
    coefficient_distribution_key = "\u6ee1\u8db3\u63d0\u989d\u6761\u4ef6\u5ba2\u6237\u7ebf\u4e0a\u914d\u7f6e\u7cfb\u6570\u5206\u5e03(cash_remark1)"
    coefficient_mismatch_key = "\u6ee1\u8db3\u63d0\u989d\u6761\u4ef6\u5ba2\u6237\u7ebf\u4e0a\u7cfb\u6570\u4e0d\u4e00\u81f4\u5ba2\u6237\u6570"
    coefficient_match_key = "\u6ee1\u8db3\u63d0\u989d\u6761\u4ef6\u5ba2\u6237\u7ebf\u4e0a\u7cfb\u6570\u4e00\u81f4\u5ba2\u6237\u6570"

    cell_rows: list[str] = []
    for row in sorted(rows, key=lambda item: item["结清客户数"], reverse=True):
        conclusion = row["策略执行结论"]
        cell_rows.append(
            f"""
            <tr data-state=\"{conclusion_class(conclusion)}\">
              <td class=\"policy\">{esc(row['策略格'])}</td>
              <td class=\"num\">{pct(row['表内目标提额系数'])}</td>
              <td class=\"num\">{integer(row['结清客户数'])}</td>
              <td class=\"num\">{integer(row['提额客户数'])}</td>
              <td class=\"num\">{integer(row['未提额客户数'])}</td>
              <td class=\"num\">{pct(row['提额覆盖率'])}</td>
              <td class=\"num\">{yuan(row['提额客户提额前平均额度(元)'])}</td>
              <td class=\"num\">{yuan(row['提额客户提额后平均额度(元)'])}</td>
              <td class=\"num positive\">{pct(row['提额客户实际提幅(加权)'])}</td>
              <td class=\"num\">{yuan(row['未提额客户提额前平均额度(元)'])}</td>
              <td class=\"num\">{yuan(row['未提额客户提额后平均额度(元)'])}</td>
              <td class=\"num\">{yuan(row['结清客户提额前平均额度(元)'])}</td>
              <td class=\"num\">{yuan(row['结清客户提额后平均额度(元)'])}</td>
              <td class=\"num positive\">{pct(row['结清客户额度提升率'])}</td>
              <td class=\"num\">{pct(row['提额客户T0发起率'])}</td>
              <td class=\"num\">{pct(row['未提额客户T0发起率'])}</td>
              <td class=\"num\">{pct(row['提额客户下一笔发起率'])}</td>
              <td class=\"num\">{pct(row['未提额客户下一笔发起率'])}</td>
              <td class=\"num\">{pct(row['提额客户FPD1'])} <small>n={integer(row['提额客户FPD1样本'])}</small></td>
              <td class=\"num\">{pct(row['未提额客户FPD1'])} <small>n={integer(row['未提额客户FPD1样本'])}</small></td>
              <td class=\"num\">{pct(row['提额客户FPD7'])} <small>n={integer(row['提额客户FPD7样本'])}</small></td>
              <td class=\"num\">{pct(row['未提额客户FPD7'])} <small>n={integer(row['未提额客户FPD7样本'])}</small></td>
              <td class=\"num\">{pct(row[coefficient_rate_key])}</td>
              <td class=\"configuration\">{esc(row[coefficient_distribution_key])}</td>
              <td><span class=\"tag {conclusion_class(conclusion)}\">{esc(conclusion)}</span></td>
            </tr>"""
        )

    top_rows: list[str] = []
    need_check = [row for row in rows if row["策略执行结论"] == "提额执行符合；系数需核对"]
    for i, row in enumerate(sorted(need_check, key=lambda item: item[coefficient_mismatch_key], reverse=True)[:10], 1):
        top_rows.append(
            f"""
            <tr><td class=\"rank\">{i:02d}</td><td class=\"policy\">{esc(row['策略格'])}</td>
            <td class=\"num\">{integer(row['结清客户数'])}</td><td class=\"num\">{integer(row[coefficient_mismatch_key])}</td>
            <td class=\"num\">{pct(row[coefficient_rate_key])}</td><td class=\"configuration\">{esc(row[coefficient_distribution_key])}</td></tr>"""
        )

    page = f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\"><title>提额策略执行与整体达成｜2026-08-12</title>
<style>
:root{{--ink:#172033;--muted:#667085;--line:#e5eaf2;--canvas:#f5f7fb;--surface:#fff;--blue:#3772f6;--blue-soft:#edf3ff;--green:#12976a;--green-soft:#eaf8f2;--amber:#b56700;--amber-soft:#fff6df;--red:#d7464f;--red-soft:#fff0f1;--navy:#152956;--shadow:0 12px 32px rgba(26,43,77,.07)}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.6 Inter,"PingFang SC","Microsoft YaHei",system-ui,-apple-system,sans-serif}}.shell{{width:min(1440px,calc(100% - 40px));margin:auto}}.top{{color:#fff;background:linear-gradient(110deg,#152956,#1f4ba5 64%,#3772f6)}}.top .shell{{height:48px;display:flex;justify-content:space-between;align-items:center;font-size:12px}}.brand{{font-weight:750}}.meta{{color:#dce6ff;font-size:11px}}.hero{{position:relative;overflow:hidden;padding:40px 0 64px;color:#fff;background:linear-gradient(110deg,#152956,#1d469b 58%,#3772f6)}}.hero:after{{content:"";position:absolute;right:-120px;top:-300px;width:560px;height:560px;border:1px solid rgba(255,255,255,.15);border-radius:50%;box-shadow:0 0 0 55px rgba(255,255,255,.035),0 0 0 110px rgba(255,255,255,.025)}}.hero-grid{{position:relative;z-index:1;display:grid;grid-template-columns:1fr 340px;gap:35px;align-items:end}}.eyebrow{{display:inline-flex;align-items:center;gap:7px;padding:4px 10px;border:1px solid rgba(255,255,255,.25);border-radius:999px;color:#dce8ff;font-size:11px;font-weight:700;letter-spacing:.08em}}.dot{{width:6px;height:6px;border-radius:50%;background:#7df1c2;box-shadow:0 0 0 4px rgba(125,241,194,.15)}}h1{{margin:16px 0 10px;font-size:clamp(27px,4vw,40px);line-height:1.18;letter-spacing:-.04em}}.hero p{{max-width:820px;margin:0;color:#dce6fb}}.hero-note{{margin-top:16px;color:#bbcef8;font-size:11px}}.hero-card{{padding:20px;border:1px solid rgba(255,255,255,.18);border-radius:16px;background:rgba(255,255,255,.1)}}.hero-card span,.hero-card small{{color:#d3e1fb;font-size:11px}}.hero-card strong{{display:block;margin:4px 0;font-size:30px;letter-spacing:-.055em}}main{{padding-bottom:64px}}.kpis{{position:relative;z-index:2;display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:-28px}}.kpi{{min-height:130px;position:relative;overflow:hidden;padding:16px;border:1px solid var(--line);border-radius:13px;background:var(--surface);box-shadow:var(--shadow)}}.kpi:before{{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:var(--blue)}}.kpi.green:before{{background:var(--green)}}.kpi.amber:before{{background:var(--amber)}}.kpi.red:before{{background:var(--red)}}.kpi-label{{color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.04em}}.kpi-value{{margin-top:12px;font-size:27px;font-weight:780;line-height:1;letter-spacing:-.05em}}.kpi-value small{{margin-left:2px;color:var(--muted);font-size:12px;font-weight:500;letter-spacing:0}}.kpi-foot{{margin-top:9px;color:var(--muted);font-size:10.5px;line-height:1.45}}.nav{{display:flex;gap:8px;flex-wrap:wrap;margin:25px 0 18px}}.nav a{{padding:6px 10px;border:1px solid var(--line);border-radius:7px;background:#fff;color:var(--muted);text-decoration:none;font-size:11px;font-weight:650}}.section{{margin-top:18px;padding:23px;border:1px solid var(--line);border-radius:15px;background:var(--surface);box-shadow:0 3px 10px rgba(26,43,77,.025)}}.section-head{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}}.kicker{{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.1em}}h2{{margin:3px 0 0;font-size:20px;line-height:1.35;letter-spacing:-.025em}}.desc{{max-width:800px;margin:5px 0 0;color:var(--muted);font-size:12px}}.tag{{display:inline-flex;padding:3px 7px;border:1px solid;border-radius:5px;font-size:10px;font-weight:750;white-space:nowrap}}.tag.pass{{background:var(--green-soft);border-color:#c7ecdd;color:#0b7b55}}.tag.check{{background:var(--amber-soft);border-color:#f5dfa2;color:#a46000}}.tag.empty{{background:#f1f3f6;border-color:#e1e5eb;color:#697386}}.tag.warn{{background:var(--red-soft);border-color:#f7cdd1;color:#bd3440}}.summary{{display:grid;grid-template-columns:1.12fr .88fr;gap:15px}}.callout{{padding:18px;border:1px solid #e5ebf7;border-radius:11px;background:#f7f9fd}}.callout h3{{margin:0 0 7px;font-size:15px}}.callout p{{margin:0;color:#4d5c76;font-size:12px;line-height:1.75}}.callout strong{{color:var(--red)}}.facts{{display:grid;gap:8px}}.fact{{display:grid;grid-template-columns:28px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--line)}}.fact:last-child{{border:0}}.fact-num{{width:22px;height:22px;display:grid;place-items:center;border-radius:6px;background:var(--blue-soft);color:var(--blue);font-size:10px;font-weight:800}}.fact b{{display:block;font-size:12px}}.fact span{{display:block;margin-top:1px;color:var(--muted);font-size:11px}}.compare{{display:grid;grid-template-columns:repeat(3,1fr);gap:11px}}.card{{padding:16px;border:1px solid var(--line);border-radius:11px}}.card .label{{color:var(--muted);font-size:11px;font-weight:700}}.card .number{{margin:8px 0 4px;font-size:25px;line-height:1;font-weight:780;letter-spacing:-.045em}}.card .note{{color:var(--muted);font-size:10.5px;line-height:1.55}}.card.blue{{background:linear-gradient(135deg,#fff,#f3f7ff);border-color:#d8e5fb}}.card.blue .number{{color:var(--blue)}}.card.green{{background:linear-gradient(135deg,#fff,#f2fbf7);border-color:#d2eee1}}.card.green .number{{color:var(--green)}}.card.amber{{background:linear-gradient(135deg,#fff,#fffaf0);border-color:#f2e3bb}}.card.amber .number{{color:var(--amber)}}.post-table{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.metric-table{{width:100%;border-collapse:collapse}}.metric-table th{{padding:10px 11px;background:#f5f7fb;color:#526077;border-bottom:1px solid #dfe5ef;text-align:left;font-size:10.5px}}.metric-table td{{padding:10px 11px;border-bottom:1px solid var(--line);font-size:11px}}.metric-table tr:last-child td{{border:0}}.metric-table .num{{text-align:right;font-variant-numeric:tabular-nums}}.positive{{color:var(--green);font-weight:750}}.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:11px}}table{{width:100%;border-collapse:collapse;min-width:2600px}}th{{position:sticky;top:0;z-index:1;padding:10px 11px;background:#f5f7fb;color:#526077;border-bottom:1px solid #dfe5ef;text-align:left;white-space:nowrap;font-size:10.5px;letter-spacing:.02em}}td{{padding:10px 11px;border-bottom:1px solid var(--line);color:#344054;font-size:11px;vertical-align:middle}}tbody tr:hover td{{background:#f8fbff}}td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}td.num small{{display:block;color:#98a2b3;font-size:9px;font-weight:500}}.policy{{min-width:210px;font-weight:650;color:#24334e}}.configuration{{min-width:150px;color:#526077;white-space:nowrap}}.rank{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#98a2b3;font-weight:800}}.method{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.method-box{{padding:15px;border:1px solid var(--line);border-radius:10px;background:#f6f8fc}}.method-box h3{{margin:0 0 7px;font-size:12px}}.method-box ul{{margin:0;padding-left:17px;color:var(--muted);font-size:10.5px;line-height:1.85}}code{{padding:1px 4px;border-radius:4px;background:#eef2f8;color:#354663;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.95em}}.footer{{padding:24px 0 32px;color:#98a2b3;font-size:10.5px;text-align:center}}@media(max-width:1100px){{.kpis{{grid-template-columns:repeat(3,1fr)}}.hero-grid,.summary,.post-table{{grid-template-columns:1fr}}.hero-card{{max-width:340px}}.compare{{grid-template-columns:1fr}}}}@media(max-width:650px){{.shell{{width:min(100% - 24px,1440px)}}.top .shell{{height:auto;padding:10px 0;align-items:flex-start;flex-direction:column;gap:3px}}.hero{{padding:30px 0 47px}}.kpis{{grid-template-columns:repeat(2,1fr);gap:9px;margin-top:-20px}}.kpi{{min-height:120px;padding:13px}}.section{{padding:17px}}.section-head{{flex-direction:column;gap:8px}}.method{{grid-template-columns:1fr}}}}@media print{{@page{{margin:10mm;size:landscape}}body{{background:#fff;font-size:9px}}.top{{background:#17366f!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}}.hero{{padding:20px 0 28px;-webkit-print-color-adjust:exact;print-color-adjust:exact}}.hero:after,.nav{{display:none}}.section,.kpi{{box-shadow:none;break-inside:avoid}}.section{{margin-top:9px;padding:13px}}.kpis{{margin-top:-15px}}}}
</style></head><body>
<header class=\"top\"><div class=\"shell\"><div class=\"brand\">◈ 风控 BI 平台 · 提额策略执行分析</div><div class=\"meta\">线上结果聚合 · 报告生成：2026-08-13</div></div></header>
<section class=\"hero\"><div class=\"shell hero-grid\"><div><span class=\"eyebrow\"><i class=\"dot\"></i>策略表逐行统计 · 整体达成测算</span><h1>提额策略执行与户均额度达成</h1><p>以《提额系数20260812.xlsx》315 个策略行作为分析骨架，逐行统计提额、未提额客户的额度、提幅、T0/下一笔发起及 FPD 表现；再汇总测算提额前后整体户均额度相对 5 万元目标的达成情况。</p><div class=\"hero-note\">数据表：<b>pb_biz_credit.flexi_cash_jq_result_v1</b> · <b>jq_date=2026-08-12</b> · <b>str_type=new</b> · 策略格借款数 7 = 7 及以上</div></div><div class=\"hero-card\"><span>提额后户均额度 / 目标</span><strong>{yuan(full['结清客户提额后平均额度(元)'])} / 50,000 元</strong><small>目标达成率 {pct(full['提额后目标达成率'])} · 距目标 {yuan(full['提额后户均差距(元)'])} 元/户</small></div></div></section>
<main class=\"shell\"><div class=\"kpis\"><article class=\"kpi\"><div class=\"kpi-label\">有效结清客户</div><div class=\"kpi-value\">{integer(full['结清客户数'])}<small>人</small></div><div class=\"kpi-foot\">新策略、前后额度有效</div></article><article class=\"kpi blue\"><div class=\"kpi-label\">提额前户均额度</div><div class=\"kpi-value\">{yuan(full['结清客户提额前平均额度(元)'])}<small>元</small></div><div class=\"kpi-foot\">目标达成 {pct(full['提额前目标达成率'])}</div></article><article class=\"kpi green\"><div class=\"kpi-label\">提额后户均额度</div><div class=\"kpi-value\">{yuan(full['结清客户提额后平均额度(元)'])}<small>元</small></div><div class=\"kpi-foot\">目标达成 {pct(full['提额后目标达成率'])}</div></article><article class=\"kpi amber\"><div class=\"kpi-label\">目标增量达成</div><div class=\"kpi-value\">{pct(full['目标增量达成率'])}</div><div class=\"kpi-foot\">实际增额 / 达标所需增额</div></article><article class=\"kpi\"><div class=\"kpi-label\">提额覆盖率</div><div class=\"kpi-value\">{pct(full['提额覆盖率'])}</div><div class=\"kpi-foot\">{integer(full['提额客户数'])} 名提额 / {integer(full['未提额客户数'])} 名未提额</div></article><article class=\"kpi red\"><div class=\"kpi-label\">满足提额条件客户系数一致率</div><div class=\"kpi-value\">{pct(full[coefficient_rate_key])}</div><div class=\"kpi-foot\">仅 te_flag=1；配置版本或查表键待核对</div></article></div>
<nav class=\"nav\"><a href=\"../../risk_analysis/提额策略执行分析_20260812_v2.xlsx\" download>下载逐行 Excel</a><a href=\"#attainment\">整体达成</a><a href=\"#execution\">策略执行</a><a href=\"#post\">发起与贷后</a><a href=\"#cells\">策略表逐行统计</a><a href=\"#method\">口径</a></nav>
<section id=\"attainment\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">OVERALL ATTAINMENT</div><h2>先看整体：提额把户均额度从 4.32 万推至 4.77 万，但尚未达到 5 万</h2><p class=\"desc\">这是按策略表逐行统计结果汇总后的整体测算；总量口径包含 1 条无法映射策略表的异常维度样本。</p></div><span class=\"tag check\">距目标 {yuan(full['提额后户均差距(元)'])} 元/户</span></div><div class=\"summary\"><div class=\"callout\"><h3>达成判断</h3><p>全量有效结清样本的户均额度由 <b>{yuan(full['结清客户提额前平均额度(元)'])} 元</b> 提升至 <b>{yuan(full['结清客户提额后平均额度(元)'])} 元</b>，实际增加 <strong>{yuan(full['实际总增额(元)'])} 元</strong>。若整体户均达到 50,000 元，还需要总增额 {yuan(full['达标所需总增额(元)'])} 元；当前实际完成所需增量的 <strong>{pct(full['目标增量达成率'])}</strong>。</p></div><div class=\"facts\"><div class=\"fact\"><div class=\"fact-num\">01</div><div><b>提额客户实际提幅 {pct(full['提额客户实际提幅(加权)'])}</b><span>提额客户户均由 {yuan(full['提额客户提额前平均额度(元)'])} 元升至 {yuan(full['提额客户提额后平均额度(元)'])} 元。</span></div></div><div class=\"fact\"><div class=\"fact-num\">02</div><div><b>未提额客户保持在 {yuan(full['未提额客户提额后平均额度(元)'])} 元</b><span>未提额客户占 {pct(1-full['提额覆盖率'])}，是整体距目标仍有缺口的主要结构性来源。</span></div></div><div class=\"fact\"><div class=\"fact-num\">03</div><div><b>策略表可映射样本 {integer(mapped['结清客户数'])} 人</b><span>逐行策略表合计与全量口径相差 {integer(unmapped['结清客户数'])} 条异常维度样本。</span></div></div></div></div></section>
<section id=\"execution\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">STRATEGY EXECUTION</div><h2>提额/未提额是否按策略执行：执行正确，满足提额条件客户的系数仍需按行核对</h2><p class=\"desc\">执行层面比较 <code>te_flag</code> 与实际额度变化；配置层面仅在 <code>te_flag=1</code>（满足提额条件）客户中，比较 <code>cash_remark1</code> 与策略表目标系数。</p></div><span class=\"tag pass\">执行符合率 {pct(full['提额/未提额执行符合率'])}</span></div><div class=\"compare\"><article class=\"card green\"><div class=\"label\">提额客户执行</div><div class=\"number\">{pct(full['提额客户实际提额率'])}</div><div class=\"note\">{integer(full['提额客户数'])} 名 <code>te_flag=1</code> 客户均实际提额。</div></article><article class=\"card green\"><div class=\"label\">未提额客户执行</div><div class=\"number\">{pct(full['未提额客户实际未变率'])}</div><div class=\"note\">{integer(full['未提额客户数'])} 名 <code>te_flag=0</code> 客户均额度保持不变。</div></article><article class=\"card amber\"><div class=\"label\">满足提额条件客户系数核验</div><div class=\"number\">{pct(full[coefficient_rate_key])}</div><div class=\"note\">字段为 <code>cash_remark1</code>；仅 {integer(full['提额客户数'])} 名 <code>te_flag=1</code> 客户参与。其中 {integer(full[coefficient_match_key])} 名一致、{integer(full[coefficient_mismatch_key])} 名待核对。</div></article></div></section>
<section id=\"post\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">INITIATION & POST-LOAN</div><h2>提额客户与未提额客户的发起及贷后表现</h2><p class=\"desc\">FPD 使用客户口径，且首日批次的成熟样本很少；请同时看每项后的 n 值，暂不宜据此作风险优劣结论。</p></div><span class=\"tag blue\">需关注成熟样本</span></div><div class=\"post-table\"><table class=\"metric-table\"><thead><tr><th>发起指标</th><th class=\"num\">提额客户</th><th class=\"num\">未提额客户</th></tr></thead><tbody><tr><td>T0 发起率</td><td class=\"num positive\">{pct(full['提额客户T0发起率'])}</td><td class=\"num\">{pct(full['未提额客户T0发起率'])}</td></tr><tr><td>下一笔发起率</td><td class=\"num positive\">{pct(full['提额客户下一笔发起率'])}</td><td class=\"num\">{pct(full['未提额客户下一笔发起率'])}</td></tr></tbody></table><table class=\"metric-table\"><thead><tr><th>贷后指标（客户口径）</th><th class=\"num\">提额客户</th><th class=\"num\">未提额客户</th></tr></thead><tbody><tr><td>FPD1</td><td class=\"num\">{pct(full['提额客户FPD1'])} <small>(n={integer(full['提额客户FPD1样本'])})</small></td><td class=\"num\">{pct(full['未提额客户FPD1'])} <small>(n={integer(full['未提额客户FPD1样本'])})</small></td></tr><tr><td>FPD7</td><td class=\"num\">{pct(full['提额客户FPD7'])} <small>(n={integer(full['提额客户FPD7样本'])})</small></td><td class=\"num\">{pct(full['未提额客户FPD7'])} <small>(n={integer(full['未提额客户FPD7样本'])})</small></td></tr><tr><td>FPD15</td><td class=\"num\">{pct(full['提额客户FPD15'])} <small>(n={integer(full['提额客户FPD15样本'])})</small></td><td class=\"num\">{pct(full['未提额客户FPD15'])} <small>(n={integer(full['未提额客户FPD15样本'])})</small></td></tr><tr><td>FPD30</td><td class=\"num\">{pct(full['提额客户FPD30'])} <small>(n={integer(full['提额客户FPD30样本'])})</small></td><td class=\"num\">{pct(full['未提额客户FPD30'])} <small>(n={integer(full['未提额客户FPD30样本'])})</small></td></tr></tbody></table></div></section>
<section id=\"cells\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">STRATEGY TABLE ANALYSIS</div><h2>策略表逐行统计结果</h2><p class=\"desc\">每行对应原始系数表的一格。新增列按提额/未提额客户分别展示额度、提幅、T0/下一笔发起和 FPD；可横向滚动查看。</p></div><span class=\"tag blue\">315 个策略格</span></div><div class=\"table-wrap\"><table><thead><tr><th>策略格</th><th class=\"num\">表内系数</th><th class=\"num\">结清客户</th><th class=\"num\">提额客户</th><th class=\"num\">未提额客户</th><th class=\"num\">提额覆盖率</th><th class=\"num\">提额前均额</th><th class=\"num\">提额后均额</th><th class=\"num\">实际提幅</th><th class=\"num\">未提额前均额</th><th class=\"num\">未提额后均额</th><th class=\"num\">结清前均额</th><th class=\"num\">结清后均额</th><th class=\"num\">结清增幅</th><th class=\"num\">提额T0</th><th class=\"num\">未提额T0</th><th class=\"num\">提额下一笔</th><th class=\"num\">未提额下一笔</th><th class=\"num\">提额FPD1</th><th class=\"num\">未提额FPD1</th><th class=\"num\">提额FPD7</th><th class=\"num\">未提额FPD7</th><th class=\"num\">提额客户系数一致率</th><th>提额客户 cash_remark1 分布</th><th>结论</th></tr></thead><tbody>{''.join(cell_rows)}</tbody></table></div></section>
<section id=\"method\" class=\"section\"><div class=\"section-head\"><div><div class=\"kicker\">SCOPE & METHOD</div><h2>本次应如何分析</h2></div><span class=\"tag blue\">简单、可复核</span></div><div class=\"method\"><div class=\"method-box\"><h3>正确的主线</h3><ul><li>先以策略表每一行作为分析单元，统计该格提额与未提额客户数。</li><li>比较两类客户的提额前后额度、实际提幅、T0/下一笔发起率。</li><li>按 <code>te_flag</code> 与实际额度变化验证策略是否执行。</li><li>汇总全行结果，测算提额前/后户均额度与 5 万目标的达成情况。</li><li>最后观察 FPD1/7/15/30，但必须同时保留成熟样本数。</li></ul></div><div class=\"method-box\"><h3>必要边界</h3><ul><li>策略格 7 表示借款数 7 及以上。</li><li>“提额客户 cash_remark1 分布”字段为 <code>cash_remark1</code>（线上提额幅度）；仅展示并核对 <code>te_flag=1</code>（满足提额条件）客户，未提额客户不参与系数一致客户数、不一致客户数和一致率。</li><li>正系数未提额需结合资格、拦截、封顶等闸门解释。</li><li>当前 FPD 成熟样本极少，不能据首日快照形成稳定风险结论。</li><li>本报告为聚合统计，不含客户标识与 ODPS 凭证。</li></ul></div></div></section></main><footer class=\"footer\">风控 BI 平台 · 提额策略执行与整体达成分析 · 内部聚合分析快照</footer></body></html>"""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
