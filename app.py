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

st.set_page_config(page_title="Fintech Disruption Index", layout="wide")

plt.rcParams.update({
    "figure.dpi": 130,
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
})

st.title("Fintech Two-Wave Disruption Index")
st.caption(
    "Adjust the parameters in the sidebar — the sub-indices, break dates, and "
    "Chow tests below recompute live. See `VERDICT.md` for the written analysis "
    "this app lets you stress-test, not replace."
)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

st.sidebar.header("Parameters")

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

real_data_available = all(
    os.path.exists(p) for p in (MARKET_CSV, WAVE1_TRENDS_CSV, WAVE2_TRENDS_CSV, EDGAR_CSV)
)
use_synthetic = st.sidebar.checkbox(
    "Use synthetic demo data",
    value=not real_data_available,
    disabled=not real_data_available,
    help=(
        "Real collector output not found — forced on."
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

if res.used_synthetic:
    st.warning(
        "SYNTHETIC DEMO DATA — NOT A REAL RESULT. This is fabricated placeholder "
        "data built to demo the method end to end; it is not evidence for or "
        "against the two-wave thesis."
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


col1, col2 = st.columns(2)
with col1:
    st.pyplot(render_two_wave(df, breaks), clear_figure=True)
with col2:
    st.pyplot(render_momentum(df, momentum_window), clear_figure=True)

# ---------------------------------------------------------------------------
# Break / Chow test results
# ---------------------------------------------------------------------------

st.subheader("Detected structural breaks")

metric_cols = st.columns(3)
for c, series_name, label in zip(metric_cols, ("wave1", "wave2", "FDI"),
                                 ("Wave 1", "Wave 2", "Composite FDI")):
    c.metric(f"{label} breaks", breaks["series"][series_name]["n_breaks"])

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
    st.markdown(table_df.to_html(index=False), unsafe_allow_html=True)
else:
    st.info("No breaks detected at this penalty / window setting.")

st.caption(
    f"FDI = {w1_weight:.2f} × Wave1 + {1 - w1_weight:.2f} × Wave2 · "
    f"PELT penalty = {pelt_penalty} · momentum window = {momentum_window} months"
    + (" · **SYNTHETIC**" if res.used_synthetic else "")
)

# ---------------------------------------------------------------------------
# AI Research Assistant (Groq) -- grounded in the exact df/breaks computed
# above, so it can't drift from the sliders or invent statistics not present
# in this run. Stateless per call: every question rebuilds the context fresh
# from whatever the sliders are set to *right now*.
# ---------------------------------------------------------------------------

st.divider()
st.subheader("🤖 AI Research Assistant")

api_key = os.environ.get("GROQ_API_KEY") or st.session_state.get("groq_api_key")

if not api_key:
    st.caption(
        "Grounded in the exact numbers computed above -- ask questions or "
        "generate a live executive summary reflecting the current sliders."
    )
    with st.expander("Enter a Groq API key to enable this section", expanded=True):
        key_input = st.text_input(
            "Groq API key", type="password",
            help="Free, no billing card required, at "
                 "https://console.groq.com/keys. Kept only in this "
                 "session's memory -- never written to disk.",
        )
        if key_input:
            st.session_state["groq_api_key"] = key_input
            st.rerun()
    st.caption("Or set a `GROQ_API_KEY` environment variable before launching the app.")
else:
    context = ai_assistant.build_data_context(
        df, breaks, w1_weight, pelt_penalty, momentum_window, res.used_synthetic
    )

    tab_summary, tab_chat = st.tabs(["Live summary", "Ask a question"])

    with tab_summary:
        st.caption(
            "Regenerates an executive-summary paragraph reflecting the "
            "*current* slider settings -- compare it against VERDICT.md's "
            "written analysis at the default 50/50 weight."
        )
        if st.button("Generate summary"):
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
            "Answers are grounded in the numbers shown above -- ask about "
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
