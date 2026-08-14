# -*- coding: utf-8 -*-
"""生成 8/13 结清 提额效果分析 HTML 报告(风险等级×策略类型×是否提额) v2"""
import json

d = json.load(open("risk_analysis/effect_framework_0813.json", encoding="utf-8"))
def g(st, sc, te):
    return d.get(f"('{st}', '{sc}', '{te}')")

def fnum(v, dec=0):
    if v is None: return '<span class="muted">—</span>'
    return f"{v:,.{dec}f}"

def fpct(v, dec=1):
    if v is None: return '<span class="muted">—</span>'
    return f"{v*100:.{dec}f}%"

def fpd(v, s):
    if v is None or s == 0: return '<span class="muted">—</span>'
    return f"{v*100:.1f}%<span class='n'>({s})</span>"

# ---------- 主表行: 客户数带占比(占该风险等级该策略全部客户) ----------
def row(sc, st):
    r = g(st, sc, "提额客户"); n = g(st, sc, "未提额客户"); dn = g(st, sc, "降额客户")
    total = sum((c["客户数"] for c in (r, n, dn) if c), 0)
    cells = []
    for label, cell in (("提额客户", r), ("未提额客户", n), ("降额客户", dn)):
        if cell is None:
            cells.append(f"<td class='empty' colspan='10'></td>")
            continue
        ratio = cell["客户数"] / total if total else 0
        cells.append(f"""
<td class='grp'>{label}<span class='n'>{cell['客户数']:,} · {ratio:.1%}</span></td>
<td>{fnum(cell['提额前平均额度(元)'])}</td>
<td>{fnum(cell['提额后平均额度(元)'])}</td>
<td class='{"up" if (cell["额度提升率"] or 0)>0 else ""}'>{fpct(cell["额度提升率"]) if cell["额度提升率"] is not None else "<span class='muted'>—</span>"}</td>
<td class='mini'><span class='bar' style='width:{min((cell["提额前额度使用率"] or 0)*100, 100)}%'></span>{fpct(cell["提额前额度使用率"])}</td>
<td>{fnum(cell['提额前借款金额(元)'])}</td>
<td>{fnum(cell['提额后借款金额(元)'])}</td>
<td class='mini'><span class='bar' style='width:{min((cell["提额后额度使用率"] or 0)*100, 100)}%'></span>{fpct(cell["提额后额度使用率"])}</td>
<td>{fpd(cell["fpd7"], cell["fpd7样本"])}</td>
<td>{fpd(cell["fpd1"], cell["fpd1样本"])}</td>""")
    return "<tr><th class='score'>" + sc + "</th>" + "".join(cells) + "</tr>"

METRICS = "客户数</th><th>提额前<br/>平均额度</th><th>提额后<br/>平均额度</th><th>额度<br/>提升率</th><th>提额前<br/>使用率</th><th>提额前<br/>借款金额</th><th>提额后<br/>借款金额</th><th>提额后<br/>使用率</th><th>fpd7</th><th>fpd1"

def section(title, st, note):
    head = f"""
    <h2>{title}</h2><p class="note">{note}</p>
    <table>
      <thead><tr>
        <th rowspan="2">风险等级</th>
        <th colspan="10">提额客户</th>
        <th colspan="10">未提额客户</th>
        <th colspan="10">降额客户(te_flag=2)</th>
      </tr><tr>
        <th>{METRICS}</th><th>{METRICS}</th><th>{METRICS}</th>
      </tr></thead><tbody>"""
    rows = "".join(row(sc, st) for sc in "ABCDE")
    return head + rows + "</tbody></table>"

# ---------- 新旧策略交易额增量对比(含客户数/未提额客户数/占比) ----------
def delta_section():
    def v(st, sc, te, key):
        cell = g(st, sc, te)
        return cell.get(key) if cell else None
    lines = []
    total_delta = total_cnt = 0.0
    head = """
    <h2>新旧策略 实际交易额增量对比(交易额 = 下一笔借款 loan_prin,元)</h2>
    <p class="note">三级分组: 第一级指标 → 第二级策略(新/旧) → 第三级客户(提额/未提额)。提额净效应 = 提额客户人均下一笔 − 未提额客户人均下一笔(以未提额为基线);净增量 = 新策略净效应 − 旧策略净效应。<br/>
    折算总增量 = 提额客户人均增量(新−旧) × 新策略提额客户数(万元)。</p>
    <table>
      <thead><tr>
        <th rowspan="3">风险<br/>等级</th>
        <th colspan="4">客户数<br/>(占比/覆盖率)</th>
        <th colspan="2">结清平均<br/>借款金额(元)</th>
        <th colspan="5">人均下一笔借款(元)</th>
        <th colspan="3">提额净效应(元/人)<br/><span class='subth'>= 提额客户 − 未提额客户</span></th>
        <th rowspan="3">折算总增量<br/>(万元, 口径1)</th>
      </tr><tr>
        <th colspan="2">新策略</th><th colspan="2">旧策略</th>
        <th>新策略</th><th>旧策略</th>
        <th colspan="2">新策略</th><th colspan="2">旧策略</th><th>增量(新−旧)<br/><span class='subth'>提额客户</span></th>
        <th>新策略</th><th>旧策略</th><th>净增量(新−旧)</th>
      </tr><tr>
        <th>提额</th><th>未提额</th><th>提额</th><th>未提额</th>
        <th></th><th></th>
        <th>提额</th><th>未提额</th><th>提额</th><th>未提额</th><th></th>
        <th>提额−未提额</th><th>提额−未提额</th><th></th>
      </tr></thead><tbody>"""
    for sc in "ABCDE":
        new_raise = v("new", sc, "提额客户", "提额后借款金额(元)")
        old_raise = v("old", sc, "提额客户", "提额后借款金额(元)")
        new_non = v("new", sc, "未提额客户", "提额后借款金额(元)")
        old_non = v("old", sc, "未提额客户", "提额后借款金额(元)")
        new_cnt = v("new", sc, "提额客户", "客户数")
        old_cnt = v("old", sc, "提额客户", "客户数")
        new_ncnt = v("new", sc, "未提额客户", "客户数")
        old_ncnt = v("old", sc, "未提额客户", "客户数")
        if new_raise is None or old_raise is None:
            lines.append(f"<tr><th class='score'>{sc}</th><td class='empty' colspan='16'>新策略无提额(E 级不参与提额)</td></tr>")
            continue
        new_tot = sum((c["客户数"] for te in ("提额客户", "未提额客户", "降额客户") if (c := g("new", sc, te))), 0)
        old_tot = sum((c["客户数"] for te in ("提额客户", "未提额客户", "降额客户") if (c := g("old", sc, te))), 0)
        def grp_loan(st):
            num = cnt = 0
            for te in ("提额客户", "未提额客户", "降额客户"):
                c = g(st, sc, te)
                if c:
                    num += c["提额前借款金额(元)"] * c["客户数"]
                    cnt += c["客户数"]
            return num / cnt if cnt else None
        new_loan = grp_loan("new")
        old_loan = grp_loan("old")
        new_cov = new_cnt / new_tot if new_tot else 0
        old_cov = old_cnt / old_tot if old_tot else 0
        new_nr = new_ncnt / new_tot if new_tot else 0
        old_nr = old_ncnt / old_tot if old_tot else 0
        d1 = new_raise - old_raise
        ne_new = (new_raise - new_non) if new_non is not None else None
        ne_old = (old_raise - old_non) if old_non is not None else None
        d2 = (ne_new - ne_old) if (ne_new is not None and ne_old is not None) else None
        total = d1 * new_cnt
        total_delta += total; total_cnt += new_cnt
        cls = lambda x: " up" if (x or 0) > 0 else (" down" if (x or 0) < 0 else "")
        lines.append(f"<tr><th class='score'>{sc}</th>"
            f"<td>{new_cnt:,.0f} · {new_cov:.1%}</td><td>{new_ncnt:,.0f} · {new_nr:.1%}</td>"
            f"<td>{old_cnt:,.0f} · {old_cov:.1%}</td><td>{old_ncnt:,.0f} · {old_nr:.1%}</td>"
            f"<td>{new_loan:,.0f}</td><td>{old_loan:,.0f}</td>"
            f"<td>{new_raise:,.0f}</td><td>{new_non:,.0f}</td><td>{old_raise:,.0f}</td><td>{old_non:,.0f}</td><td class='{cls(d1)}'>{d1:+,.0f}</td>"
            f"<td class='{cls(ne_new)}'>{ne_new:+,.0f}</td><td class='{cls(ne_old)}'>{ne_old:+,.0f}</td><td class='{cls(d2)}'>{d2:+,.0f}</td>"
            f"<td class='up'>{total/1e4:,.0f}</td></tr>")
    def grp(st, te):
        total_sum = total_cnt = starter_cnt = 0
        for sc in "ABCDE":
            c = g(st, sc, te)
            if c:
                total_sum += c["提额后借款金额(元)"] * c["客户数"] * c["下一笔发起率"]
                starter_cnt += c["客户数"] * c["下一笔发起率"]
                total_cnt += c["客户数"]
        return (total_sum, total_cnt, starter_cnt)
    n_r, n_rc, n_rk = grp("new", "提额客户"); o_r, o_rc, o_rk = grp("old", "提额客户")
    n_n, n_nc, n_nk = grp("new", "未提额客户"); o_n, o_nc, o_nk = grp("old", "未提额客户")
    n_tot = n_rc + n_nc + sum((c["客户数"] for sc in "ABCDE" if (c := g("new", sc, "降额客户"))), 0)
    o_tot = o_rc + o_nc + sum((c["客户数"] for sc in "ABCDE" if (c := g("old", sc, "降额客户"))), 0)
    def grp_loan_all(st):
        num = cnt = 0
        for sc in "ABCDE":
            for te in ("提额客户", "未提额客户", "降额客户"):
                c = g(st, sc, te)
                if c:
                    num += c["提额前借款金额(元)"] * c["客户数"]
                    cnt += c["客户数"]
        return num / cnt if cnt else 0
    n_loan_all = grp_loan_all("new")
    o_loan_all = grp_loan_all("old")
    n_r_avg, o_r_avg = n_r / n_rk if n_rk else 0, o_r / o_rk if o_rk else 0
    n_n_avg, o_n_avg = n_n / n_nk if n_nk else 0, o_n / o_nk if o_nk else 0
    d1t = n_r_avg - o_r_avg
    net_new, net_old = n_r_avg - n_n_avg, o_r_avg - o_n_avg
    d2t = net_new - net_old
    lines.append(f"<tr><th class='score'>合计</th>"
        f"<td>{n_rc:,.0f} · {n_rc/n_tot:.1%}</td><td>{n_nc:,.0f} · {n_nc/n_tot:.1%}</td>"
        f"<td>{o_rc:,.0f} · {o_rc/o_tot:.1%}</td><td>{o_nc:,.0f} · {o_nc/o_tot:.1%}</td>"
        f"<td>{n_loan_all:,.0f}</td><td>{o_loan_all:,.0f}</td>"
        f"<td>{n_r_avg:,.0f}</td><td>{n_n_avg:,.0f}</td><td>{o_r_avg:,.0f}</td><td>{o_n_avg:,.0f}</td><td class='up'>{d1t:+,.0f}</td>"
        f"<td class='up'>{net_new:+,.0f}</td><td class='down'>{net_old:+,.0f}</td><td class='up'>{d2t:+,.0f}</td>"
        f"<td class='up'>{total_delta/1e4:,.0f}</td></tr>")
    lines.append(f"<tr><td colspan='17' class='note2'>口径1 总增量 ≈ {total_delta/1e4:,.0f} 万元(提额客户人均增量 {d1t:+,.0f} 元 × 新策略提额客户 {total_cnt:,.0f} 人); 口径2 净增量 ≈ {d2t*total_cnt/1e4:,.0f} 万元(净增量 {d2t:+,.0f} 元 × 新策略提额客户)。净增量 = 新策略净效应({net_new:+,.0f}) − 旧策略净效应({net_old:+,.0f})。人均下一笔为'已发起下一笔客户'均值(未发起为NULL不计入)。举例: 新A净效应 +2,171 = 提额客户 32,262 − 未提额客户 30,091。</td></tr>")
    return head + "".join(lines) + "</tbody></table>"

# ---------- 各等级交易额净增量变化分析 ----------
def delta_analysis():
    def v(st, sc, te, key):
        cell = g(st, sc, te)
        return cell.get(key) if cell else None
    rows_data = []
    for sc in "ABCDE":
        nr = v("new", sc, "提额客户", "提额后借款金额(元)")
        orr = v("old", sc, "提额客户", "提额后借款金额(元)")
        nn = v("new", sc, "未提额客户", "提额后借款金额(元)")
        on = v("old", sc, "未提额客户", "提额后借款金额(元)")
        if nr is None or orr is None: continue
        ne_new = nr - nn if nn is not None else None
        ne_old = orr - on if on is not None else None
        d2 = (ne_new - ne_old) if (ne_new is not None and ne_old is not None) else None
        rows_data.append((sc, ne_new, ne_old, d2, nr, orr))
    rows_data.sort(key=lambda x: x[3] if x[3] is not None else -1e18, reverse=True)
    bars = ""
    for sc, ne_new, ne_old, d2, nr, orr in rows_data:
        w = min(abs(d2) / 9000 * 100, 100) if d2 else 0
        pos = d2 is not None and d2 > 0
        bars += f"<div class='dbar'><span class='dl'>{sc} 级</span><span class='dbg'><span class='dbfill' style='width:{w:.0f}%'></span></span><span class='dv'>{d2:+,.0f} 元/人</span></div>"
    max_sc, max_d2 = rows_data[0][0], rows_data[0][3]
    min_sc, min_d2 = rows_data[-1][0], rows_data[-1][3]
    def row_info(sc):
        for r in rows_data:
            if r[0] == sc: return r
        return None
    html = f"""
    <h2>各风险等级 交易额净增量变化(口径2: 新策略提额净效应 − 旧策略提额净效应)</h2>
    <div class="dbarwrap">{bars}</div>
    <div class="concl">
    <h3>📊 各等级净增量解读</h3>
    <ol>
    <li><b>{max_sc} 级净增量最大({max_d2:+,.0f} 元/人)</b>:新策略 {max_sc} 级提额客户人均下一笔 {rows_data[0][4]:,.0f} 元,高于本组未提额客户;而旧策略 {max_sc} 级提额客户显著低于未提额——新策略在 {max_sc} 级实现了"提额即增交易",提额对象筛选精准。</li>
    <li><b>B 级净增量 {row_info('B')[3]:+,.0f} 元/人</b>:新 B 级提额客户(5,253 人,覆盖率 {g('new','B','提额客户')['客户数']/(g('new','B','提额客户')['客户数']+g('new','B','未提额客户')['客户数']):.1%})人均下一笔 {row_info('B')[4]:,.0f} 元,相对旧策略 B 级提额({row_info('B')[5]:,.0f} 元)提升 {row_info('B')[4]/row_info('B')[5]-1:+.0%}。</li>
    <li><b>C 级净增量最小({row_info('C')[3]:+,.0f} 元/人)</b>:新 C 级提额客户下一笔 {row_info('C')[4]:,.0f} 元,与未提额差距最大——C 级提额客户是低额度客群(提额后均额 3.0万),交易量上不去;新旧策略在此级几乎无差异,是下一轮提额调优的重点。</li>
    <li><b>E 级无增量</b>:新策略提额资格不含 E 级(高风险),E 级客户(4,791 人)全部未提额。</li>
    <li><b>覆盖率结构</b>:新策略提额高度集中于 A/B/C 级(覆盖率 66%~69%),D 级仅 2.6%(223 人)、E 级 0%——提额资源与风险档严格挂钩,但 D 级中"低风险 D"(fpd7&lt;大盘)仍有可挖空间。</li>
    </ol>
    </div>"""
    return html

# ---------- 按结清日期汇总表(8/8-8/13) ----------
daily = json.load(open("risk_analysis/daily_summary_0813.json", encoding="utf-8"))

DAILY_COLS = ["结清客户", "结清平均额度", "结清平均额度后", "件均", "额度使用率", "提额客户",
              "提额客户_平均额度", "提额客户_提额后平均", "发起下一笔订单", "发起下一笔件均", "平均借款天数", "下一笔日息",
              "fpd1_fm_dd", "fpd7_fm_dd", "fpd1_rate$", "fpd1_rate", "fpd7_rate$", "fpd7_rate"]

def daily_section():
    head = """
    <h2>按结清日期汇总统计(8/8 – 8/13, 全量客群)</h2>
    <p class="note">金额单位: 元 · 额度使用率 = 本笔放款/提额前额度 · 件均 = 本笔放款(loan_amount)均值 · 下一笔日息 = interest_fee_daily 均值<br/>
    fpd1/fpd7_rate = 客户口径(fz_dd/fm_dd), rate$ = 笔口径(fz_bj/fm_bj) · fpd1_fm_dd / fpd7_fm_dd 为分母样本数 · 发起下一笔订单 = next_loan_flag=1 人数</p>
    <div class="scrollx"><table>
      <thead><tr><th>日期</th>"""
    for c in DAILY_COLS:
        head += f"<th>{c}</th>"
    head += "</tr></thead><tbody>"
    rows = ""
    for d, v in daily.items():
        label = d.replace("2026-", "").replace("-", "/")
        rows += f"<tr><th class='score'>{label}</th>"
        rows += f"<td>{v['结清客户']:,}</td>"
        rows += f"<td>{v['结清平均额度']:,.0f}</td>"
        rows += f"<td>{v['结清平均额度后']:,.0f}</td>"
        rows += f"<td>{v['件均']:,.0f}</td>"
        rows += f"<td>{v['额度使用率']:.1%}</td>"
        rows += f"<td>{v['提额客户']:,}</td>"
        rows += f"<td>{v['提额客户_平均额度']:,.0f}</td>"
        rows += f"<td>{v['提额客户_提额后平均']:,.0f}</td>"
        rows += f"<td>{v['发起下一笔订单']:,}</td>"
        rows += f"<td>{v['发起下一笔件均']:,.0f}</td>"
        rows += f"<td>{v['平均借款天数']}</td>"
        rows += f"<td>{v['下一笔日息']}</td>"
        rows += f"<td>{v['fpd1_fm_dd']:,}</td><td>{v['fpd7_fm_dd']:,}</td>"
        rows += f"<td>{v['fpd1_rate$']:.1%}</td><td>{v['fpd1_rate']:.1%}</td>"
        rows += f"<td>{v['fpd7_rate$']:.1%}</td><td>{v['fpd7_rate']:.1%}</td></tr>"
    return head + rows + "</tbody></table></div>"

html = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>20260813 结清 · 提额效果分析</title>
<style>
:root{--brand:#537D96;--brand2:#3F6179;--bg:#F5F1E8;--card:#FFFFFF;--ink:#2A2622;--mut:#8F867B;--line:#E4DBC8}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;background:linear-gradient(160deg,#F5F1E8 0%,#EDE7D9 100%);color:var(--ink);padding:32px 28px}
.wrap{max-width:1500px;margin:0 auto}
h1{font-size:22px;font-weight:700;letter-spacing:.5px}
.sub{color:var(--mut);font-size:12.5px;margin:6px 0 22px;line-height:1.8}
h2{font-size:15px;margin:26px 0 6px;color:var(--brand2);border-left:4px solid var(--brand);padding-left:10px}
.note{font-size:12px;color:var(--mut);margin-bottom:10px}
table{border-collapse:collapse;width:100%;background:var(--card);border-radius:10px;overflow:hidden;box-shadow:0 4px 20px rgba(42,38,34,.08);font-size:12px;margin-bottom:10px}
th{background:var(--brand);color:#FBF7EE;padding:8px 6px;font-weight:600;text-align:center;white-space:nowrap;border:1px solid var(--brand2)}
thead tr:first-child th{font-size:12.5px}
tr.cols2 th{background:var(--brand2);font-size:11px;font-weight:400}
.subth{font-size:10px;font-weight:400;opacity:.8}
td{border:1px solid #EEE6D6;padding:7px 6px;text-align:center;white-space:nowrap}
td.grp{font-weight:600;color:var(--brand2);background:#F6F2E9}
th.score{background:#6E91A6;width:44px;font-size:14px}
td.empty{background:#FAF7F0}
td.up{color:#C0392B;font-weight:600}
td.down{color:#1E8449;font-weight:600}
td.mini{position:relative;min-width:70px}
span.bar{position:absolute;left:2px;bottom:2px;height:3px;background:linear-gradient(90deg,var(--brand),#8FB3C8);border-radius:2px;opacity:.85}
span.n{color:var(--mut);font-size:10px;margin-left:2px}
span.muted{color:#C4BBA8}
.scrollx{overflow-x:auto;border-radius:10px}
.scrollx table{margin-bottom:0}
td.ghost{background:transparent;border:none;width:8px}
td.note2{background:#F6F2E9;color:var(--brand2);font-size:11px;text-align:left;padding:8px 12px;line-height:1.7}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:14px 0 6px}
.kpi{background:var(--card);border-radius:10px;padding:14px 16px;box-shadow:0 4px 20px rgba(42,38,34,.08)}
.kpi .v{font-size:19px;font-weight:700;color:var(--brand2)}
.kpi .l{font-size:11.5px;color:var(--mut);margin-top:3px}
.concl{background:#FBF7EE;border:1px solid #E4DBC8;border-radius:10px;padding:16px 20px;margin-top:16px;font-size:13px;line-height:1.9}
.concl h3{color:var(--brand2);font-size:14px;margin-bottom:6px}
.concl li{margin-left:20px}
.concl b{color:#8B2C1F}
.dbarwrap{background:var(--card);border-radius:10px;padding:14px 18px;box-shadow:0 4px 20px rgba(42,38,34,.08);margin-bottom:6px}
.dbar{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:12px}
.dl{width:44px;font-weight:600;color:var(--brand2)}
.dbg{flex:1;background:#EFE8D8;border-radius:6px;height:16px;overflow:hidden}
.dbfill{display:block;height:100%;background:linear-gradient(90deg,var(--brand),#8FB3C8);border-radius:6px}
.dv{width:110px;text-align:right;font-weight:600;color:var(--brand2)}
.foot{color:var(--mut);font-size:11px;margin-top:18px;text-align:center}
</style></head><body><div class="wrap">
<h1>2026-08-13 结清 · 提额效果分析</h1>
<div class="sub">数据源: pb_biz_credit.flexi_cash_jq_result_v1(结清日期 2026-08-13) · 策略表: 策略表和字典.xlsx(315格) · 交易量口径: loan_prin(下一笔借款金额,元)<br/>
额度单位: 元 · 客户数括号内占比为该风险等级内占比(覆盖率) · fpd7/fpd1 为客户口径,括号内为分母样本数(样本少时仅参考)</div>

<div class="kpis">
<div class="kpi"><div class="v">33,891</div><div class="l">新策略结清客户(提额 14,103 / 覆盖 41.6%)</div></div>
<div class="kpi"><div class="v">+43.8%</div><div class="l">新策略提额客户平均提幅</div></div>
<div class="kpi"><div class="v">19,651 元</div><div class="l">新策略提额客户人均下一笔借款(仅发起下一笔客户, 发起率 50.3%; 未提额 16,392)</div></div>
<div class="kpi"><div class="v">0.67 元</div><div class="l">每 1 元新增额度产生的下一笔交易量(总额口径)</div></div>
</div>

""" + daily_section() + """

""" + delta_section() + """

""" + delta_analysis() + """

""" + section("新策略(new)· 8/13 结清", "new", "8/13 线上已按新策略执行(315格系数一致率 99.99%);E 级无提额客户(提额资格不含 E)。") \
  + section("旧策略(old)· 8/13 结清", "old", "旧策略客群存量结清;提额客户为超低额度客群(前额 0.9万~2.1万),另有 1,195 名降额客户(te_flag=2)。") + """

<div class="concl">
<h3>📌 提额效果核心结论(修正口径: 人均下一笔=仅发起下一笔客户)</h3>
<ol>
<li><b>提额后借款金额实际是上升的</b>:按"已发起下一笔客户"统计,新策略提额客户人均下一笔借款 <b>19,651 元 &gt; 提额前本笔放款 15,095 元(+30%)</b>;分等级看 A: 23,089→32,262, B: 15,547→20,892, C: 11,720→14,349——提额客户结清后再借,金额普遍更高。</li>
<li><b>真正的瓶颈是"复借转化"而非单笔金额</b>:只有 <b>50.3%</b> 的提额客户在结清后发起了下一笔(未提额 46.2%),近一半客户结清后未再借款(loan_prin 为空)。提额扩大了授信,但一半客户没有动用新额度。</li>
<li><b>每 1 元新增额度仅带来约 0.67 元下一笔交易</b>:提额后额度使用率(总额口径)从提额前 31.4% 降至 20.6%,新增 2.06 亿额度只转化了约 1.39 亿下一笔借款——提额对交易量的拉动明显低于额度增幅。</li>
<li><b>新策略相对旧策略效率显著更高</b>:旧策略提额客户人均下一笔仅 11,897 元(新策略 19,651 元,<b>+65%</b>);旧策略提额对象是超低额度客群(前额 1.2万,提额后 1.8万),交易量天花板低;旧策略 1,195 名降额客户后续发起率仅 15%~24%(fpd1 80%+)。</li>
<li><b>风险表现:提额客户逾期率不高于未提额</b>(新策略 B 提额 fpd1 18.0% vs 未提额 18.0%;E 级未提额 fpd7=60% 为全组最高)——提额未带来额外风险,风险不是交易量不及预期的原因。</li>
<li><b>建议</b>:① 主攻复借转化——对结清后未复借的提额客户做促用(降息券、还款提醒、授信通知),把 50% 的转化率提上去;② 提额聚焦"中高额度×中高使用率"客群(20-50%提幅档);③ 高使用率客户提高提额后额度下限(当前 4,998 人提额后仍&lt;1万);④ 拉长至 T+7/T+30 复评。</li>
</ol>
</div>

<div class="foot">风控BI监控平台 · 提额效果分析 · 生成于 2026-08-14 · 金额为聚合均值,不含客户标识</div>
</div></body></html>"""

open("risk_analysis/提额效果分析_20260813_v2.html", "w", encoding="utf-8").write(html)
print("Wrote risk_analysis/提额效果分析_20260813_v2.html")
