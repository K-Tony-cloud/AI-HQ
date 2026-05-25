"""Shared UI components and CSS (Thai UI)."""

import streamlit as st

_BALL_GRADIENTS = [
    "radial-gradient(circle at 35% 35%, #FF6B6B, #C0392B)",
    "radial-gradient(circle at 35% 35%, #F5A623, #D4830A)",
    "radial-gradient(circle at 35% 35%, #4A90D9, #1A5276)",
    "radial-gradient(circle at 35% 35%, #2ECC71, #1A7A43)",
    "radial-gradient(circle at 35% 35%, #A78BFA, #5B2C6F)",
    "radial-gradient(circle at 35% 35%, #F06292, #AD1457)",
    "radial-gradient(circle at 35% 35%, #4DB6AC, #00695C)",
]

CSS = """
<style>
*, *::before, *::after { box-sizing: border-box; }

/* ─── Metrics ────────────────────────────────── */
.lao-metric-row  { display:flex; gap:.8rem; margin-bottom:1rem; flex-wrap:wrap; }
.lao-metric {
  flex:1; min-width:130px;
  background:#161B22; border:1px solid #30363D; border-radius:14px;
  padding:1rem .9rem; text-align:center; transition:border-color .2s;
}
.lao-metric:hover { border-color:#E63946; }
.lao-metric .m-icon  { font-size:1.5rem; line-height:1; }
.lao-metric .m-val   { font-size:1.75rem; font-weight:800; color:#E63946; margin:.25rem 0 .15rem; line-height:1; }
.lao-metric .m-label { font-size:.68rem; color:#8B949E; text-transform:uppercase; letter-spacing:.07em; }

/* ─── Lottery balls ──────────────────────────── */
.ball-row { display:flex; flex-wrap:wrap; gap:12px; justify-content:center; padding:1.2rem 0; }
.ball-item { display:flex; flex-direction:column; align-items:center; gap:4px; }
.lao-ball {
  width:64px; height:64px; border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:800; font-size:1.3rem;
  box-shadow:0 6px 18px rgba(0,0,0,.45), inset 0 -4px 8px rgba(0,0,0,.3);
  user-select:none;
}
.lao-ball.top { box-shadow:0 0 0 3px #FFD700, 0 6px 18px rgba(0,0,0,.45); transform:scale(1.1); }
.ball-pct { font-size:.62rem; color:#8B949E; font-weight:500; }

/* ─── Latest draw ────────────────────────────── */
.latest-card {
  background:linear-gradient(135deg,#1a0a0a 0%,#2d0f0f 100%);
  border:1px solid #E63946; border-radius:16px;
  padding:1.5rem 1.8rem; text-align:center; margin-bottom:1rem;
}
.latest-card .lc-label { color:#8B949E; font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; }
.latest-card .lc-date  { color:#F0F6FC; font-size:1rem; margin:.2rem 0 .8rem; }
.latest-card .lc-six   {
  font-size:2.8rem; font-weight:900; letter-spacing:.15em;
  background:linear-gradient(90deg,#E63946,#FFD700);
  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
}
.latest-card .lc-sub   { color:#8B949E; font-size:.9rem; margin-top:.5rem; }

/* ─── Prediction block ───────────────────────── */
.pred-block {
  background:#0D1117; border:1px solid #30363D; border-radius:16px;
  padding:1.2rem 1.4rem; margin-bottom:1rem;
}
.pred-block .pb-title {
  font-size:1rem; font-weight:700; color:#F0F6FC;
  border-left:3px solid #E63946; padding-left:.6rem;
  margin-bottom:1rem;
}
.pred-row { display:flex; flex-wrap:wrap; gap:1rem; }
.pred-type {
  flex:1; min-width:150px;
  background:#161B22; border:1px solid #30363D; border-radius:12px;
  padding:.9rem 1rem;
}
.pred-type .pt-label { font-size:.7rem; color:#8B949E; text-transform:uppercase; letter-spacing:.07em; margin-bottom:.6rem; }
.pred-item { display:flex; align-items:center; gap:.5rem; margin-bottom:.35rem; }
.pred-item .pi-rank  { font-size:.65rem; color:#8B949E; width:14px; }
.pred-item .pi-num   { font-size:1.1rem; font-weight:800; color:#F0F6FC; min-width:40px; }
.pred-item .pi-bar-wrap { flex:1; background:#30363D; border-radius:4px; height:6px; }
.pred-item .pi-bar   { background:linear-gradient(90deg,#E63946,#FFD700); height:6px; border-radius:4px; }
.pred-item .pi-pct   { font-size:.65rem; color:#8B949E; width:36px; text-align:right; }

/* ─── Stale banner ───────────────────────────── */
.stale-banner {
  background:#2d1f00; border:1px solid #F5A623; border-radius:10px;
  padding:.7rem 1rem; color:#F5A623; font-size:.85rem;
  margin-bottom:1rem; display:flex; align-items:center; gap:.6rem;
}

/* ─── Section label ──────────────────────────── */
.sec-label {
  font-size:1rem; font-weight:600; color:#F0F6FC;
  border-left:3px solid #E63946; padding-left:.65rem;
  margin:1.3rem 0 .65rem;
}

/* ─── Nav cards ──────────────────────────────── */
.nav-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:.9rem; }
.nav-card {
  background:#161B22; border:1px solid #30363D; border-radius:12px;
  padding:1.2rem 1.1rem; transition:border-color .2s;
}
.nav-card:hover { border-color:#E63946; }
.nav-card .nc-icon { font-size:1.8rem; }
.nav-card h4 { margin:.35rem 0 .25rem; color:#F0F6FC; font-size:.95rem; }
.nav-card p  { margin:0; color:#8B949E; font-size:.8rem; line-height:1.4; }

/* ─── Accuracy badge ─────────────────────────── */
.acc-badge {
  display:inline-block; border-radius:20px; padding:.2rem .6rem;
  font-size:.75rem; font-weight:700;
}
.acc-badge.high { background:#1a3a1a; color:#2ECC71; border:1px solid #2ECC71; }
.acc-badge.mid  { background:#3a2a00; color:#F5A623; border:1px solid #F5A623; }
.acc-badge.low  { background:#3a0a0a; color:#E63946; border:1px solid #E63946; }

/* ─── Tabs ───────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { gap:.4rem; }
.stTabs [data-baseweb="tab"] {
  background:#161B22 !important; border-radius:8px !important;
  border:1px solid #30363D !important; color:#8B949E !important;
  padding:.4rem .9rem !important;
}
.stTabs [aria-selected="true"] {
  background:#E63946 !important; color:#fff !important;
  border-color:#E63946 !important;
}

/* ─── Sidebar ────────────────────────────────── */
div[data-testid="stSidebar"] { background:#0D1117 !important; }
div[data-testid="stSidebar"] hr { border-color:#30363D; }

/* ─── Mobile ─────────────────────────────────── */
@media (max-width:768px) {
  .lao-metric     { min-width:100px; padding:.8rem .6rem; }
  .lao-metric .m-val { font-size:1.4rem; }
  .lao-ball       { width:52px; height:52px; font-size:1.05rem; }
  .ball-row        { gap:8px; }
  .latest-card .lc-six { font-size:2rem; }
  .nav-grid        { grid-template-columns:1fr 1fr; }
  .pred-row        { flex-direction:column; }
}
</style>
"""

_CHART = dict(
    plot_bgcolor="#161B22", paper_bgcolor="#0D1117",
    font_color="#F0F6FC", margin=dict(t=30, b=40, l=40, r=20),
)


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chart_style(**kw) -> dict:
    return {**_CHART, **kw}


def metric_row(metrics: list[tuple]) -> None:
    cards = "".join(
        f'<div class="lao-metric"><div class="m-icon">{ic}</div>'
        f'<div class="m-val">{val}</div><div class="m-label">{lbl}</div></div>'
        for ic, val, lbl in metrics
    )
    st.markdown(f'<div class="lao-metric-row">{cards}</div>', unsafe_allow_html=True)


def lottery_balls(numbers: list[str], scores: list[float] | None = None) -> None:
    items = []
    for i, num in enumerate(numbers):
        grad  = _BALL_GRADIENTS[i % len(_BALL_GRADIENTS)]
        cls   = "lao-ball top" if i == 0 else "lao-ball"
        score = f'<div class="ball-pct">{scores[i]:.1f}%</div>' if scores else ""
        items.append(
            f'<div class="ball-item"><div class="{cls}" style="background:{grad}">{num}</div>{score}</div>'
        )
    st.markdown(f'<div class="ball-row">{"".join(items)}</div>', unsafe_allow_html=True)


def prediction_block(pred_groups: dict[str, list[dict]]) -> None:
    """
    pred_groups: { digit_type: [ {number, probability}, ... ] }
    Shows a styled prediction card per digit type.
    """
    from src.database import DIGIT_LABEL
    type_items = []
    for dtype, preds in pred_groups.items():
        label = DIGIT_LABEL.get(dtype, dtype)
        rows_html = ""
        max_prob = max((p["probability"] for p in preds), default=1) or 1
        for i, p in enumerate(preds[:5]):
            bar_w = min(100, round(p["probability"] / max_prob * 100))
            rows_html += (
                f'<div class="pred-item">'
                f'<span class="pi-rank">#{i+1}</span>'
                f'<span class="pi-num">{p["number"]}</span>'
                f'<div class="pi-bar-wrap"><div class="pi-bar" style="width:{bar_w}%"></div></div>'
                f'<span class="pi-pct">{p["probability"]:.1f}%</span>'
                f'</div>'
            )
        type_items.append(
            f'<div class="pred-type"><div class="pt-label">{label}</div>{rows_html}</div>'
        )

    st.markdown(
        f'<div class="pred-block">'
        f'<div class="pb-title">🎯 ผลการทำนายล่าสุด</div>'
        f'<div class="pred-row">{"".join(type_items)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def latest_draw_card(six: str, date_str: str, last_4: str, top_3: str, last_2: str) -> None:
    st.markdown(
        f'<div class="latest-card">'
        f'<div class="lc-label">ผลรางวัลล่าสุด</div>'
        f'<div class="lc-date">{date_str}</div>'
        f'<div class="lc-six">{six}</div>'
        f'<div class="lc-sub">'
        f'4 ตัวท้าย: <strong>{last_4}</strong>'
        f' &nbsp;·&nbsp; 3 ตัวบน: <strong>{top_3}</strong>'
        f' &nbsp;·&nbsp; 2 ตัวล่าง: <strong>{last_2}</strong>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def stale_banner(last_scraped: str) -> None:
    st.markdown(
        f'<div class="stale-banner">⚠ ข้อมูลอาจล้าสมัย — '
        f'อัปเดตล่าสุด: {last_scraped} '
        f'ไปที่ <strong>⚙️ ตั้งค่า</strong> เพื่อรีเฟรช</div>',
        unsafe_allow_html=True,
    )


def section_label(text: str) -> None:
    st.markdown(f'<div class="sec-label">{text}</div>', unsafe_allow_html=True)


def nav_cards(cards: list[tuple]) -> None:
    items = "".join(
        f'<div class="nav-card"><div class="nc-icon">{ic}</div>'
        f'<h4>{title}</h4><p>{desc}</p></div>'
        for ic, title, desc in cards
    )
    st.markdown(f'<div class="nav-grid">{items}</div>', unsafe_allow_html=True)


def accuracy_badge(pct: float) -> str:
    cls = "high" if pct >= 50 else "mid" if pct >= 25 else "low"
    return f'<span class="acc-badge {cls}">{pct:.1f}%</span>'
