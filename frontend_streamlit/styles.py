"""
styles.py
---------
Custom CSS + small HTML component builders (KPI cards, risk badges, cards).

NOTE: HTML strings passed to st.markdown are collapsed onto a single line
(see `_h`) because Markdown treats indented lines as code blocks.
"""
from __future__ import annotations

from html import escape
from typing import Dict, List, Optional, Sequence, Tuple

from data_utils import RISK_COLORS, RISK_TINTS, RISK_TEXT, RISK_FILL_TEXT, RISK_MEANING, fmt_int, impact_band


def _h(html: str) -> str:
    """Collapse multi-line HTML to one line (avoids Markdown code-block parsing)."""
    return " ".join(line.strip() for line in html.strip().splitlines() if line.strip())


CSS = _h("<style>") + """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--ink:#10231E;--muted:#5B6F68;--brand:#0E7C4A;--brand-dark:#0A5C38;--accent:#F2A93B;--bg:#F3F6F4;--card:#FFFFFF;--line:#DCE5E0;}
html, body, .stApp{font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;}
.stApp{background:var(--bg);}
.block-container{padding-top:1.3rem;padding-bottom:3rem;max-width:1400px;}
header[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer{visibility:hidden;}

.hero{background:linear-gradient(120deg,#0A3D2A 0%,#0E7C4A 62%,#2FA36B 100%);border-radius:18px;padding:26px 32px;color:#fff;
      display:flex;justify-content:space-between;align-items:center;gap:24px;box-shadow:0 10px 28px rgba(10,61,42,.20);}
.hero-title{font-size:2.05rem;font-weight:800;letter-spacing:-.02em;line-height:1.15;color:#fff;}
.hero-title span{color:#FFD98A;}
.hero-sub{margin-top:6px;color:rgba(255,255,255,.86);font-size:.98rem;}
.hero-chips{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;}
.chip{background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.30);color:#fff;border-radius:999px;padding:6px 14px;font-size:.78rem;font-weight:600;white-space:nowrap;}
.disclaimer{background:#FFF6E0;border:1px solid #F2D48B;border-left:5px solid #F2A93B;color:#5C4310;border-radius:10px;
            padding:11px 16px;margin:14px 0 18px 0;font-size:.88rem;line-height:1.45;}

.kpi{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--brand);border-radius:14px;padding:15px 18px 14px 18px;
     box-shadow:0 1px 2px rgba(16,35,30,.05);min-height:118px;}
.kpi .label{font-size:.70rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700;}
.kpi .value{font-size:1.85rem;font-weight:800;color:var(--ink);line-height:1.15;margin-top:6px;}
.kpi .sub{font-size:.76rem;color:var(--muted);margin-top:4px;}
.kpi.danger{border-top-color:#C62F3B;} .kpi.danger .value{color:#C62F3B;}
.kpi.ok{border-top-color:#2E9E5B;} .kpi.ok .value{color:#1E7A43;}
.kpi.info{border-top-color:#1B4D6B;}
.kpi .bar{height:6px;background:#E6EEEA;border-radius:6px;margin-top:9px;overflow:hidden;}
.kpi .bar>span{display:block;height:100%;background:var(--brand);border-radius:6px;}

.section-title{font-size:1.08rem;font-weight:700;color:var(--ink);margin:6px 0 2px 0;}
.section-sub{color:var(--muted);font-size:.85rem;margin-bottom:10px;}

.risk-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.risk{border-radius:12px;padding:13px 16px;border:1px solid;display:flex;justify-content:space-between;align-items:center;}
.risk .name{font-weight:800;letter-spacing:.07em;font-size:.78rem;}
.risk .desc{font-size:.72rem;opacity:.85;margin-top:2px;}
.risk .count{font-size:2rem;font-weight:800;line-height:1;}

.priority{background:#FFFFFF;border:1px solid var(--line);border-left:7px solid #C62F3B;border-radius:14px;padding:20px 24px;box-shadow:0 1px 2px rgba(16,35,30,.05);}
.priority .tag{font-size:.70rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700;}
.priority .name{font-size:1.5rem;font-weight:800;color:var(--ink);margin:4px 0 6px 0;}
.priority .reason{color:#2B3F39;font-size:.95rem;line-height:1.55;margin-bottom:12px;}
.priority .stats{display:flex;gap:26px;flex-wrap:wrap;}
.priority .stat .k{font-size:.70rem;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:600;}
.priority .stat .v{font-size:1.25rem;font-weight:800;color:var(--ink);}
.pill{display:inline-block;color:#fff;border-radius:999px;padding:3px 12px;font-size:.72rem;font-weight:800;letter-spacing:.06em;vertical-align:middle;margin-left:8px;}

.fest{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:14px;box-shadow:0 1px 2px rgba(16,35,30,.05);}
.fest .head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;}
.fest .fname{font-size:1.08rem;font-weight:800;color:var(--ink);}
.fest .uplift{font-size:1.55rem;font-weight:800;line-height:1;}
.fest .meta{color:var(--muted);font-size:.82rem;margin:8px 0 10px 0;line-height:1.5;}
.fest .meta b{color:var(--ink);}
.fest .sku-row{display:flex;justify-content:space-between;font-size:.84rem;padding:5px 0;border-top:1px dashed var(--line);}
.fest .sku-row .pct{font-weight:700;color:#0A5C38;}

[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:0 1px 2px rgba(16,35,30,.04);}
[data-testid="stMetricLabel"]{color:var(--muted);}
.stTabs [data-baseweb="tab-list"]{gap:6px;border-bottom:1px solid var(--line);}
.stTabs [data-baseweb="tab"]{height:46px;padding:0 20px;font-weight:600;}
div[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;}
.filter-title{font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700;margin-bottom:2px;}
.status-pill{display:inline-block;border-radius:999px;padding:4px 12px;font-size:.78rem;font-weight:700;}
.status-ok{background:#E8F6EE;color:#1E7A43;border:1px solid #BFE3CD;}
.status-bad{background:#FBE6E8;color:#A32530;border:1px solid #F1BBC0;}
""" + _h("</style>")


# ---------------------------------------------------------------- builders
def hero() -> str:
    return _h("""
    <div class="hero">
      <div>
        <div class="hero-title">DMart <span>SmartStock</span> AI</div>
        <div class="hero-sub">Inventory-constrained demand forecasting &amp; smart stock allocation for a simulated retail chain</div>
      </div>
      <div class="hero-chips">
        <span class="chip">Simulated data</span>
        <span class="chip">RandomForest forecasts</span>
        <span class="chip">Priority-based allocation</span>
      </div>
    </div>
    """)


def disclaimer() -> str:
    return _h("""
    <div class="disclaimer"><b>Synthetic / simulated data.</b> All branch sales, inventory and warehouse figures shown here are
    randomly generated for demonstration purposes. They are <b>not</b> real DMart data, and this project is not affiliated with or
    endorsed by DMart / Avenue Supermarts Ltd.</div>
    """)


def section(title: str, sub: str = "") -> str:
    sub_html = f'<div class="section-sub">{escape(sub)}</div>' if sub else ""
    return _h(f'<div class="section-title">{escape(title)}</div>{sub_html}')


def kpi_card(label: str, value: str, sub: str = "", tone: str = "", bar_pct: Optional[float] = None) -> str:
    bar = ""
    if bar_pct is not None:
        bar = f'<div class="bar"><span style="width:{max(0.0, min(100.0, bar_pct)):.1f}%"></span></div>'
    return _h(f"""
    <div class="kpi {escape(tone)}"><div class="label">{escape(label)}</div><div class="value">{escape(value)}</div>
    <div class="sub">{escape(sub)}</div>{bar}</div>
    """)


def risk_grid(counts: Sequence[Tuple[str, int]]) -> str:
    cells: List[str] = []
    for level, n in counts:
        color, tint, text = RISK_COLORS[level], RISK_TINTS[level], RISK_TEXT[level]
        cells.append(
            f'<div class="risk" style="background:{tint};border-color:{color}88;color:{text}">'
            f'<div><div class="name">{level}</div><div class="desc">{escape(RISK_MEANING[level])}</div></div>'
            f'<div class="count">{n}</div></div>'
        )
    return _h(f'<div class="risk-grid">{"".join(cells)}</div>')


def risk_pill(level: str) -> str:
    return (f'<span class="pill" style="background:{RISK_COLORS.get(level, "#888")};'
            f'color:{RISK_FILL_TEXT.get(level, "#fff")}">{escape(level)}</span>')


def priority_card(branch_name: str, branch_id: str, reason: str, risk: str,
                  stats: Dict[str, str], tag: str = "Highest priority branch") -> str:
    color = RISK_COLORS.get(risk, "#C62F3B")
    stat_html = "".join(
        f'<div class="stat"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div></div>'
        for k, v in stats.items()
    )
    return _h(f"""
    <div class="priority" style="border-left-color:{color}">
      <div class="tag">{escape(tag)}</div>
      <div class="name">{escape(branch_name)} <span style="color:#5B6F68;font-weight:600;font-size:1rem">({escape(branch_id)})</span>{risk_pill(risk)}</div>
      <div class="reason"><b>Why:</b> {escape(reason)}</div>
      <div class="stats">{stat_html}</div>
    </div>
    """)


def festival_card(f: Dict) -> str:
    pct = float(f.get("expected_demand_increase_pct", 0))
    band, color = impact_band(pct)
    skus = "".join(
        f'<div class="sku-row"><span>{escape(str(s.get("product_name", s.get("sku_id"))))} '
        f'<span style="color:#5B6F68">({escape(str(s.get("sku_id", "")))})</span></span>'
        f'<span class="pct">{float(s.get("pct_increase", 0)):+.1f}%</span></div>'
        for s in f.get("high_risk_skus", [])
    )
    return _h(f"""
    <div class="fest">
      <div class="head">
        <div><div class="fname">{escape(str(f.get("festival", "")))}</div>
             <span class="pill" style="background:{color};color:{'#3D2B00' if color == RISK_COLORS['MEDIUM'] else '#fff'};margin-left:0">{band.upper()} IMPACT</span></div>
        <div class="uplift" style="color:{color}">{pct:+.1f}%</div>
      </div>
      <div class="meta">Avg <b>{float(f.get("avg_units_on_festival", 0)):.1f}</b> units/day on the festival vs
        <b>{float(f.get("avg_units_baseline", 0)):.1f}</b> on a normal day.<br>
        Recommended extra buffer: <b>{fmt_int(f.get("recommended_additional_inventory", 0))} units</b></div>
      <div style="font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#5B6F68;font-weight:700;margin-bottom:2px">Top SKUs by demand jump</div>
      {skus}
    </div>
    """)


def status_pill(ok: bool, text: str) -> str:
    return f'<span class="status-pill {"status-ok" if ok else "status-bad"}">&#9679; {escape(text)}</span>'
