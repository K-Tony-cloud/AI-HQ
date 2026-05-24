"""Shared UI components and CSS for LAO-LOTTO-AI."""

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
/* ─── Reset / base ────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }

/* ─── Metric cards ────────────────────────────── */
.lao-metric-row {
  display: flex; gap: .8rem; margin-bottom: 1rem; flex-wrap: wrap;
}
.lao-metric {
  flex: 1; min-width: 130px;
  background: #161B22; border: 1px solid #30363D; border-radius: 14px;
  padding: 1rem .9rem; text-align: center;
  transition: border-color .2s;
}
.lao-metric:hover { border-color: #E63946; }
.lao-metric .m-icon  { font-size: 1.5rem; line-height: 1; }
.lao-metric .m-val   {
  font-size: 1.75rem; font-weight: 800; color: #E63946;
  margin: .25rem 0 .15rem; line-height: 1;
}
.lao-metric .m-label {
  font-size: .68rem; color: #8B949E;
  text-transform: uppercase; letter-spacing: .07em;
}

/* ─── Lottery balls ──────────────────────────── */
.ball-row {
  display: flex; flex-wrap: wrap; gap: 12px;
  justify-content: center; padding: 1.2rem 0;
}
.ball-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.lao-ball {
  width: 64px; height: 64px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 800; font-size: 1.3rem;
  box-shadow: 0 6px 18px rgba(0,0,0,.45), inset 0 -4px 8px rgba(0,0,0,.3);
  user-select: none;
}
.lao-ball.top {
  box-shadow: 0 0 0 3px #FFD700, 0 6px 18px rgba(0,0,0,.45);
  transform: scale(1.1);
}
.ball-pct { font-size: .62rem; color: #8B949E; font-weight: 500; }

/* ─── Section label ──────────────────────────── */
.sec-label {
  font-size: 1rem; font-weight: 600; color: #F0F6FC;
  border-left: 3px solid #E63946; padding-left: .65rem;
  margin: 1.3rem 0 .65rem;
}

/* ─── Latest draw card ───────────────────────── */
.latest-card {
  background: linear-gradient(135deg, #1a0a0a 0%, #2d0f0f 100%);
  border: 1px solid #E63946;
  border-radius: 16px; padding: 1.5rem 1.8rem;
  text-align: center; margin-bottom: 1rem;
}
.latest-card .lc-label { color: #8B949E; font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }
.latest-card .lc-date  { color: #F0F6FC; font-size: 1rem; margin: .2rem 0 .8rem; }
.latest-card .lc-six   {
  font-size: 2.8rem; font-weight: 900; letter-spacing: .15em;
  background: linear-gradient(90deg, #E63946, #FFD700);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.latest-card .lc-sub   { color: #8B949E; font-size: .9rem; margin-top: .5rem; }

/* ─── Stale banner ───────────────────────────── */
.stale-banner {
  background: #2d1f00; border: 1px solid #F5A623;
  border-radius: 10px; padding: .7rem 1rem;
  color: #F5A623; font-size: .85rem; margin-bottom: 1rem;
  display: flex; align-items: center; gap: .6rem;
}

/* ─── Nav cards ──────────────────────────────── */
.nav-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: .9rem;
}
.nav-card {
  background: #161B22; border: 1px solid #30363D; border-radius: 12px;
  padding: 1.2rem 1.1rem; transition: border-color .2s;
}
.nav-card:hover { border-color: #E63946; }
.nav-card .nc-icon { font-size: 1.8rem; }
.nav-card h4 { margin: .35rem 0 .25rem; color: #F0F6FC; font-size: .95rem; }
.nav-card p  { margin: 0; color: #8B949E; font-size: .8rem; line-height: 1.4; }

/* ─── Tab overrides ──────────────────────────── */
.stTabs [data-baseweb="tab-list"] { gap: .4rem; }
.stTabs [data-baseweb="tab"] {
  background: #161B22 !important; border-radius: 8px !important;
  border: 1px solid #30363D !important; color: #8B949E !important;
  padding: .4rem .9rem !important;
}
.stTabs [aria-selected="true"] {
  background: #E63946 !important; color: #fff !important;
  border-color: #E63946 !important;
}

/* ─── Sidebar ────────────────────────────────── */
div[data-testid="stSidebar"] { background: #0D1117 !important; }
div[data-testid="stSidebar"] hr { border-color: #30363D; }

/* ─── Mobile ─────────────────────────────────── */
@media (max-width: 768px) {
  .lao-metric-row { gap: .5rem; }
  .lao-metric     { min-width: 100px; padding: .8rem .6rem; }
  .lao-metric .m-val { font-size: 1.4rem; }
  .lao-ball       { width: 52px; height: 52px; font-size: 1.05rem; }
  .ball-row       { gap: 8px; }
  .latest-card .lc-six { font-size: 2rem; }
  .nav-grid { grid-template-columns: 1fr 1fr; }
}
</style>
"""

_CHART_STYLE = dict(
    plot_bgcolor="#161B22",
    paper_bgcolor="#0D1117",
    font_color="#F0F6FC",
    margin=dict(t=30, b=40, l=40, r=20),
)


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chart_style(**kwargs) -> dict:
    return {**_CHART_STYLE, **kwargs}


def metric_row(metrics: list[tuple[str, str, str]]) -> None:
    """metrics: [(icon, value, label), ...]"""
    cards = "".join(
        f'<div class="lao-metric">'
        f'<div class="m-icon">{ic}</div>'
        f'<div class="m-val">{val}</div>'
        f'<div class="m-label">{lbl}</div>'
        f'</div>'
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


def latest_draw_card(six_digit: str, draw_date: str, last_3: str, last_2: str) -> None:
    st.markdown(
        f"""
        <div class="latest-card">
          <div class="lc-label">Latest Draw</div>
          <div class="lc-date">{draw_date}</div>
          <div class="lc-six">{six_digit}</div>
          <div class="lc-sub">Last 3 digits: <strong>{last_3}</strong>
            &nbsp;·&nbsp; Last 2 digits: <strong>{last_2}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def stale_banner(last_scraped: str) -> None:
    st.markdown(
        f'<div class="stale-banner">⚠ Data may be outdated — '
        f'last scraped {last_scraped}. '
        f'Go to <strong>⚙ Settings</strong> to refresh.</div>',
        unsafe_allow_html=True,
    )


def section_label(text: str) -> None:
    st.markdown(f'<div class="sec-label">{text}</div>', unsafe_allow_html=True)


def nav_cards(cards: list[tuple[str, str, str]]) -> None:
    """cards: [(icon, title, description), ...]"""
    items = "".join(
        f'<div class="nav-card"><div class="nc-icon">{ic}</div>'
        f'<h4>{title}</h4><p>{desc}</p></div>'
        for ic, title, desc in cards
    )
    st.markdown(f'<div class="nav-grid">{items}</div>', unsafe_allow_html=True)
