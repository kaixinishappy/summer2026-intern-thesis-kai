"""
app.py
======
Interactive Streamlit app: adjust the composite weight, PELT break-detection
penalty, and momentum window live, and watch the Wave 1 / Wave 2 sub-indices,
detected break dates, and Chow test results recompute in real time.

Reuses build_index.py's loaders/index construction/break detection and
make_charts.py's color palette + break-annotation helper directly, so the
live app can never silently drift from the CLI pipeline's numbers.

Run:
    pip install streamlit
    streamlit run app.py

Needs the same real collector output as build_index.py (data/raw/*.csv,
tracked in this repo). If any is missing, the sidebar's synthetic toggle is
forced on automatically -- unlike build_index.py's CLI, which fails loudly
by design (see its docstring). The on-screen badge always says which mode
you're looking at, and moving sliders never changes which *data* is loaded,
only how it's combined/tested.
"""

import io
import os

from dotenv import load_dotenv
# Anchored to this file's directory, not the current working directory, so
# `streamlit run app.py` finds .env regardless of where it's launched from.
# Reads GROQ_API_KEY (and anything else in .env, gitignored) into
# os.environ -- a no-op if the file doesn't exist, so this is safe to run
# even before you've created one.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import matplotlib
matplotlib.use("Agg")  # must come before pyplot import: Streamlit runs this
# script off the main thread, and matplotlib's default macOS/Cocoa backend
# is not thread-safe there -- omitting this causes a hard segfault, not a
# Python exception, so it can't be caught, only avoided.
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import ai_assistant
from build_index import (
    EDGAR_CSV,
    FUNDAMENTALS_CSV,
    MARKET_CSV,
    MOMENTUM_WINDOW,
    PELT_PENALTY,
    W1_WEIGHT,
    WAVE1_TRENDS_CSV,
    WAVE2_TRENDS_CSV,
    build_indices,
    run_break_analysis,
)
from make_charts import C_FDI, C_W1, C_W2, _annotate_breaks

# pandas 3.x defaults to PyArrow-backed string dtype for CSV columns
# (future.infer_string=True). Constructing that dtype off the main thread --
# which is exactly how Streamlit runs this script -- segfaults inside
# pandas/core/arrays/string_arrow.py on this pandas/pyarrow build (confirmed
# via PYTHONFAULTHANDLER=1 stack trace, crashing in build_index.py's
# load_market() -> pd.read_csv()). Falling back to classic numpy object-dtype
# strings avoids that code path. Must be set before build_indices() is first
# called, below -- that's what actually triggers the read_csv calls.
pd.set_option("future.infer_string", False)

st.set_page_config(page_title="Fintech Disruption Index", layout="wide",
                   page_icon=":material/show_chart:")

plt.rcParams.update({
    "figure.dpi": 130,
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
})

# ---------------------------------------------------------------------------
# Styling. Colors/fonts/radius/borders all live in .streamlit/config.toml
# (native theming), not here -- it's the maintainable path and survives
# Streamlit updates, unlike hand-rolled CSS. The one exception below is the
# break-results table: st.dataframe()/st.table() both serialize through
# PyArrow, which segfaults off the main thread on this pandas/pyarrow build
# (see the comment further down), so that table is rendered as plain HTML
# via pandas' to_html() -- which has no native styling of its own and so
# still needs a small CSS assist to look like the rest of the app.
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    .block-container table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .block-container th, .block-container td { padding: 0.45rem 0.7rem; text-align: right;
                                                 border-bottom: 1px solid rgba(127, 127, 127, 0.18); }
    .block-container th { font-weight: 600; opacity: 0.75; border-bottom: 2px solid rgba(127, 127, 127, 0.3); }
    .block-container th:first-child, .block-container td:first-child { text-align: left; }
    </style>
    """,
    unsafe_allow_html=True,
)

header_placeholder = st.empty()

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

st.sidebar.header(":material/tune: Parameters")

w1_weight = st.sidebar.slider(
    "Wave 1 weight in composite FDI", 0.0, 1.0, W1_WEIGHT, 0.05,
    help="FDI = weight × Wave1 + (1 − weight) × Wave2. Default 0.5 = equal blend.",
)
pelt_penalty = st.sidebar.slider(
    "PELT penalty", 0.5, 10.0, PELT_PENALTY, 0.5,
    help="Higher = fewer, more conservative breaks. Default 3.0.",
)
momentum_window = st.sidebar.slider(
    "Momentum window (months)", 3, 24, MOMENTUM_WINDOW, 1,
    help="Breaks are detected on this trailing window's rate of change, not the raw index level.",
)

st.sidebar.divider()

real_data_available = all(
    os.path.exists(p) for p in
    (MARKET_CSV, FUNDAMENTALS_CSV, WAVE1_TRENDS_CSV, WAVE2_TRENDS_CSV, EDGAR_CSV)
)
use_synthetic = st.sidebar.checkbox(
    "Use synthetic demo data",
    value=not real_data_available,
    disabled=not real_data_available,
    help=(
        "Real collector output not found, so this is forced on."
        if not real_data_available
        else "Real data found. Check this to preview the method on fabricated "
             "placeholder data instead (built by construction, not evidence)."
    ),
)

# ---------------------------------------------------------------------------
# Recompute live (Streamlit reruns this script top-to-bottom on every
# widget change, so no manual "update" step is needed)
# ---------------------------------------------------------------------------

try:
    res = build_indices(weight_w1=w1_weight, use_synthetic=use_synthetic)
except FileNotFoundError as e:
    st.error(
        f"Real collector output missing and synthetic mode is off: {e}\n\n"
        "Run collect_market_data.py / collect_trends.py / collect_edgar.py first, "
        "or check the synthetic toggle above."
    )
    st.stop()

breaks = run_break_analysis(res, momentum_window=momentum_window, pelt_penalty=pelt_penalty)
df = res.df

badge_color, badge_icon, badge_text = (
    ("orange", ":material/science:", "Synthetic demo") if res.used_synthetic
    else ("green", ":material/verified:", "Real data")
)
with header_placeholder.container():
    with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
        st.title("Fintech Two-Wave Disruption Index")
        st.badge(badge_text, icon=badge_icon, color=badge_color)
    st.caption("Adjust the parameters in the sidebar. The sub-indices, "
              "break dates, and Chow tests below recompute live.")

if res.used_synthetic:
    st.warning(
        "This is fabricated placeholder data built to demo the method end to "
        "end; it is not evidence for or against the two-wave thesis.",
        icon=":material/science:",
        title="Synthetic demo data, not a real result",
    )

# ---------------------------------------------------------------------------
# Charts -- same palette/annotation style as make_charts.py's static PNGs
# ---------------------------------------------------------------------------


def render_two_wave(df: pd.DataFrame, breaks: dict):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df.index, df["wave1"], color=C_W1, lw=2.2, label="Wave 1 (payments / neobanks)")
    ax.plot(df.index, df["wave2"], color=C_W2, lw=2.2, label="Wave 2 (AI-native finance)")
    ax.plot(df.index, df["FDI"], color=C_FDI, lw=1.6, ls=":", label="Composite FDI")
    _annotate_breaks(ax, breaks["series"]["wave1"]["break_dates"], C_W1, "W1 break")
    _annotate_breaks(ax, breaks["series"]["wave2"]["break_dates"], C_W2, "W2 break")
    ax.axhline(0, color="black", lw=0.6, alpha=0.4)
    ax.set_title("The Two Waves of Fintech Disruption", fontweight="bold", loc="left")
    ax.set_ylabel("Standardised index (z-score)")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout()
    return fig


def render_momentum(df: pd.DataFrame, window: int):
    m1 = df["wave1"].diff(window)
    m2 = df["wave2"].diff(window)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df.index, m1, color=C_W1, lw=2.2, label="Wave 1 momentum")
    ax.plot(df.index, m2, color=C_W2, lw=2.2, label="Wave 2 momentum")
    ax.fill_between(df.index, 0, m1, where=(m1 < 0), color=C_W1, alpha=0.10)
    ax.axhline(0, color="black", lw=0.7, alpha=0.5)
    ax.set_title(f"Momentum ({window}-month change)", fontweight="bold", loc="left")
    ax.set_ylabel("Change in sub-index")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout()
    return fig


def _png_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    return buf.getvalue()


col1, col2 = st.columns(2)
with col1:
    with st.container(border=True):
        fig_two_wave = render_two_wave(df, breaks)
        two_wave_png = _png_bytes(fig_two_wave)
        st.pyplot(fig_two_wave, clear_figure=True)
        st.download_button("Download chart (PNG)", two_wave_png,
                           file_name="two_wave_index.png", mime="image/png",
                           icon=":material/download:", width="stretch", key="dl_two_wave_png")
with col2:
    with st.container(border=True):
        fig_momentum = render_momentum(df, momentum_window)
        momentum_png = _png_bytes(fig_momentum)
        st.pyplot(fig_momentum, clear_figure=True)
        st.download_button("Download chart (PNG)", momentum_png,
                           file_name="momentum_handoff.png", mime="image/png",
                           icon=":material/download:", width="stretch", key="dl_momentum_png")

# ---------------------------------------------------------------------------
# Break / Chow test results
# ---------------------------------------------------------------------------

st.subheader("Detected structural breaks")

metric_cols = st.columns(3)
for c, series_name, label in zip(metric_cols, ("wave1", "wave2", "FDI"),
                                 ("Wave 1", "Wave 2", "Composite FDI")):
    c.metric(f"{label} breaks", breaks["series"][series_name]["n_breaks"], border=True)

rows = []
for series_name, label in (("wave1", "Wave 1"), ("wave2", "Wave 2"), ("FDI", "Composite FDI")):
    for ct in breaks["series"][series_name]["chow_tests"]:
        rows.append({
            "Series": label,
            "Break date": ct.get("break_date"),
            "Chow F-stat": ct.get("F_stat"),
            "p-value": ct.get("p_value"),
            "Significant (5%)": ct.get("significant_5pct"),
        })

if rows:
    # st.dataframe()/st.table() both serialize through PyArrow
    # (streamlit/dataframe_util.py -> pyarrow.pandas_compat), which segfaults
    # off the main thread on this pyarrow build -- same underlying issue as
    # the future.infer_string fix above, different call site. Rendering as
    # plain HTML via pandas' to_html() avoids PyArrow entirely.
    table_df = pd.DataFrame(rows)
    table_df["Chow F-stat"] = table_df["Chow F-stat"].map(lambda x: f"{x:.3f}")
    table_df["p-value"] = table_df["p-value"].map(lambda x: f"{x:.5f}")
    with st.container(border=True):
        st.markdown(table_df.to_html(index=False), unsafe_allow_html=True)
else:
    st.info("No breaks detected at this penalty / window setting.")

export_col1, export_col2 = st.columns(2)
with export_col1:
    st.download_button(
        "Download full index data (CSV)", df.to_csv().encode("utf-8"),
        file_name="fdi.csv", mime="text/csv", icon=":material/download:",
        width="stretch", key="dl_fdi_csv",
        help="Monthly wave1/wave2/FDI values and their raw inputs, at the current slider settings.",
    )
with export_col2:
    st.download_button(
        "Download break/Chow results (CSV)",
        pd.DataFrame(rows).to_csv(index=False).encode("utf-8") if rows else b"",
        file_name="break_results.csv", mime="text/csv", icon=":material/download:",
        width="stretch", disabled=not rows, key="dl_breaks_csv",
        help="The table above, at the current slider settings.",
    )

with st.container(border=True):
    st.caption(
        "FDI = {:.2f} × Wave1 + {:.2f} × Wave2 &nbsp;·&nbsp; "
        "PELT penalty = {} &nbsp;·&nbsp; momentum window = {} months{}".format(
            w1_weight, 1 - w1_weight, pelt_penalty, momentum_window,
            " &nbsp;·&nbsp; **synthetic**" if res.used_synthetic else "",
        )
    )

# ---------------------------------------------------------------------------
# AI Research Assistant (Groq) -- grounded in the exact df/breaks computed
# above, so it can't drift from the sliders or invent statistics not present
# in this run. Stateless per call: every question rebuilds the context fresh
# from whatever the sliders are set to *right now*.
# ---------------------------------------------------------------------------

st.subheader(":material/smart_toy: AI research assistant")

api_key = os.environ.get("GROQ_API_KEY") or st.session_state.get("groq_api_key")

if not api_key:
    st.caption(
        "Grounded in the exact numbers computed above, ask questions or "
        "generate a live executive summary reflecting the current sliders."
    )
    with st.expander("Enter a Groq API key to enable this section", expanded=True,
                     icon=":material/key:"):
        key_input = st.text_input(
            "Groq API key", type="password",
            help="Free, no billing card required, at "
                 "https://console.groq.com/keys. Kept only in this "
                 "session's memory, never written to disk.",
        )
        if key_input:
            st.session_state["groq_api_key"] = key_input
            st.rerun()
    st.caption("Or set a `GROQ_API_KEY` environment variable before launching the app.")
else:
    context = ai_assistant.build_data_context(
        df, breaks, w1_weight, pelt_penalty, momentum_window, res.used_synthetic
    )

    tab_summary, tab_chat = st.tabs([
        ":material/summarize: Live summary", ":material/chat: Ask a question",
    ])

    with tab_summary:
        st.caption(
            "Regenerates an executive-summary paragraph reflecting the "
            "*current* slider settings. Compare it against VERDICT.md's "
            "written analysis at the default 50/50 weight."
        )
        if st.button("Generate summary", icon=":material/auto_awesome:", type="primary"):
            with st.spinner("Asking Groq..."):
                try:
                    st.session_state["ai_summary"] = ai_assistant.generate_summary(context, api_key)
                except Exception as e:
                    st.session_state["ai_summary"] = None
                    st.error(f"Groq request failed: {e}")
        if st.session_state.get("ai_summary"):
            st.markdown(st.session_state["ai_summary"])

    with tab_chat:
        st.caption(
            "Answers are grounded in the numbers shown above, ask about "
            "specific breaks, values, or what the limitations mean."
        )
        if "ai_chat_history" not in st.session_state:
            st.session_state["ai_chat_history"] = []

        for msg in st.session_state["ai_chat_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        question = st.chat_input("Ask about the findings...")
        if question:
            st.session_state["ai_chat_history"].append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        answer = ai_assistant.answer_question(
                            question, context, api_key,
                            history=st.session_state["ai_chat_history"][:-1],
                        )
                    except Exception as e:
                        answer = f"Groq request failed: {e}"
                st.markdown(answer)
            st.session_state["ai_chat_history"].append({"role": "assistant", "content": answer})
