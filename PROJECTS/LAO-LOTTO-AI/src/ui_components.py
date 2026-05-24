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

_CSS = """
<style>
/* ─── Metric cards ─────────────────────────── */
.lao-metric-row { display:flex; gap:1rem; margin-bottom:1rem; flex-wrap:wrap; }
.lao-metric {
  flex:1; min-width:140px;
  background:#161B22; border:1px solid #30363D; border-radius:14px;
  padding:1.2rem 1rem; text-align:center;
}
.lao-metric .m-icon  { font-size:1.6rem; }
.lao-metric .m-val   { font-size:1.9rem; font-weight:800; color:#E63946; margin:4px 0 2px; line-height:1; }
.lao-metric .m-label { font-size:0.72rem; color:#8B949E; text-transform:uppercase; letter-spacing:.06em; }

/* ─── Lottery balls ─────────────────────────── */
.ball-row { display:flex; flex-wrap:wrap; gap:14px; justify-content:center; padding:1.4rem 0; }
.ball-item { display:flex; flex-direction:column; align-items:center; gap:5px; }
.lao-ball {
  width:66px; height:66px; border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:800; font-size:1.35rem;
  box-shadow: 0 6px 18px rgba(0,0,0,.45), inset 0 -4px 8px rgba(0,0,0,.3);
  user-select:none;
}
.lao-ball.top { box-shadow:0 0 0 3px #FFD700, 0 6px 18px rgba(0,0,0,.45); }
.ball-pct { font-size:.65rem; color:#8B949E; }

/* ─── Section label ─────────────────────────── */
.sec-label {
  font-size:1rem; font-weight:600; color:#F0F6FC;
  border-left:3px solid #E63946; padding-left:.65rem;
  margin:1.4rem 0 .7rem;
}

/* ─── Nav cards ─────────────────────────────── */
.nav-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:1rem; }
.nav-card {
  background:#161B22; border:1px solid #30363D; border-radius:12px;
  padding:1.3rem 1.2rem;
}
.nav-card .nc-icon { font-size:2rem; }
.nav-card h4 { margin:.4rem 0 .3rem; color:#F0F6FC; font-size:1rem; }
.nav-card p  { margin:0; color:#8B949E; font-size:.82rem; line-height:1.4; }

/* ─── Overrides ─────────────────────────────── */
div[data-testid="stSidebar"] { background:#0D1117 !important; }
div[data-testid="stSidebar"] hr { border-color:#30363D; }
.stTabs [data-baseweb="tab-list"] { gap:.5rem; }
.stTabs [data-baseweb="tab"] {
  background:#161B22 !important; border-radius:8px !important;
  border:1px solid #30363D !important; color:#8B949E !important;
}
.stTabs [aria-selected="true"] {
  background:#E63946 !important; color:#fff !important;
  border-color:#E63946 !important;
}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def metric_row(metrics: list[tuple[str, str, str]]) -> None:
    """metrics: list of (icon, value, label)"""
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
            f'<div class="ball-item">'
            f'<div class="{cls}" style="background:{grad}">{num}</div>'
            f'{score}</div>'
        )
    st.markdown(
        f'<div class="ball-row">{"".join(items)}</div>',
        unsafe_allow_html=True,
    )


def section_label(text: str) -> None:
    st.markdown(f'<div class="sec-label">{text}</div>', unsafe_allow_html=True)


def nav_cards(cards: list[tuple[str, str, str]]) -> None:
    """cards: list of (icon, title, description)"""
    items = "".join(
        f'<div class="nav-card"><div class="nc-icon">{ic}</div>'
        f'<h4>{title}</h4><p>{desc}</p></div>'
        for ic, title, desc in cards
    )
    st.markdown(f'<div class="nav-grid">{items}</div>', unsafe_allow_html=True)
