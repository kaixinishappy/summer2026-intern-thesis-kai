/* app.js -- dashboard wiring: state, tabs, sidebar controls, tables,
   markdown rendering, AI assistant, robustness agent. */

(() => {
  const state = {
    w1_weight: 0.5,
    pelt_penalty: 3.0,
    momentum_window: 12,
    use_synthetic: false,
    realDataAvailable: true,
    lastIndex: null,
    dataCollectionLoaded: false,
    robustnessChecksLoaded: false,
    convergenceLoaded: false,
    verdictLoaded: false,
    chatHistory: [],
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  function fmt(x, decimals = 3) {
    if (x === null || x === undefined || Number.isNaN(x)) return "n/a";
    return Number(x).toFixed(decimals);
  }
  function fmtMoney(x) {
    if (x === null || x === undefined) return "n/a";
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(x);
  }

  // -------------------------------------------------------------- theme --

  function initTheme() {
    const saved = localStorage.getItem("theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    $("#theme-toggle").addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme")
        || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
      rerenderVisibleCharts();
    });
  }

  function rerenderVisibleCharts() {
    if (state.lastIndex) renderIndexTabs(state.lastIndex);
    if (state.dataCollectionLoaded) renderDataCollection(state._dc);
    if (state.robustnessChecksLoaded) renderRobustnessChecks(state._rc);
    if (state.convergenceLoaded) renderConvergence(state._conv);
  }

  // -------------------------------------------------------------- tabs --

  function initTabs() {
    $$(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".tab-btn").forEach((b) => b.classList.remove("active"));
        $$(".tab-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const panel = $(`#tab-${btn.dataset.tab}`);
        panel.classList.add("active");
        onTabShown(btn.dataset.tab);
        resizeChartsIn(panel);
      });
    });
    $$(".ai-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        $$(".ai-tab-btn").forEach((b) => b.classList.remove("active"));
        $$(".ai-panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        $(`#ai-${btn.dataset.aiTab}`).classList.add("active");
      });
    });
  }

  function resizeChartsIn(panel) {
    // Charts rendered while their tab was still hidden (display:none) get a
    // stale, too-narrow width baked in -- Plotly's ResizeObserver doesn't
    // reliably fire on a none->block transition, and re-calling Plotly.react
    // (which onTabShown already does for the live-index tabs) doesn't force a
    // resize by itself. Explicitly resizing every chart in the now-visible
    // panel is the only reliable fix; harmless no-op on charts already sized
    // correctly. rAF so it runs after the class toggle above has painted.
    requestAnimationFrame(() => {
      panel.querySelectorAll(".chart").forEach((el) => {
        if (el.data) Plotly.Plots.resize(el);
      });
    });
  }

  function onTabShown(tab) {
    if (tab === "data-collection" && !state.dataCollectionLoaded) loadDataCollection();
    if (tab === "robustness" && !state.robustnessChecksLoaded) loadRobustnessChecks();
    if (tab === "convergence" && !state.convergenceLoaded) loadConvergence();
    if (tab === "verdict" && !state.verdictLoaded) loadVerdict();
    if (tab === "convergence" && state.convergenceLoaded) renderConvergence(state._conv);
    if ((tab === "index-construction" || tab === "structural-breaks") && state.lastIndex) {
      renderIndexTabs(state.lastIndex); // Plotly needs a resize/re-render once its div is visible
    }
  }

  // -------------------------------------------------------------- badge --

  function updateBadge(payload) {
    const badge = $("#data-badge");
    if (payload.used_synthetic) {
      badge.className = "badge badge-warning";
      badge.textContent = payload.forced_synthetic
        ? "⚠ Synthetic demo (real data not found)"
        : "⚠ Synthetic demo data";
    } else {
      badge.className = "badge badge-good";
      badge.textContent = "✓ Real data";
    }
  }

  // ------------------------------------------------- sidebar / live index --

  function currentParams() {
    return {
      w1_weight: state.w1_weight,
      pelt_penalty: state.pelt_penalty,
      momentum_window: state.momentum_window,
      synthetic: state.use_synthetic,
    };
  }

  let fetchTimer = null;
  function scheduleIndexFetch() {
    clearTimeout(fetchTimer);
    fetchTimer = setTimeout(fetchIndex, 250);
  }

  async function fetchIndex() {
    try {
      const payload = await Api.index(currentParams());
      state.lastIndex = payload;
      updateBadge(payload);
      renderIndexTabs(payload);
      renderOverviewStats(payload);
    } catch (e) {
      console.error(e);
    }
  }

  function initSidebar(status) {
    state.w1_weight = status.defaults.w1_weight;
    state.pelt_penalty = status.defaults.pelt_penalty;
    state.momentum_window = status.defaults.momentum_window;
    state.realDataAvailable = status.real_data_available;

    $("#w1_weight").value = state.w1_weight;
    $("#pelt_penalty").value = state.pelt_penalty;
    $("#momentum_window").value = state.momentum_window;
    $("#w1_weight_val").textContent = fmt(state.w1_weight, 2);
    $("#pelt_penalty_val").textContent = fmt(state.pelt_penalty, 1);
    $("#momentum_window_val").textContent = state.momentum_window;

    if (!status.real_data_available) {
      $("#use_synthetic").checked = true;
      $("#use_synthetic").disabled = true;
      $("#synthetic-hint").textContent = "Real collector output not found on this server, so synthetic mode is forced on.";
      state.use_synthetic = true;
    } else {
      $("#synthetic-hint").textContent = "Real data found. Check this to preview the method on fabricated placeholder data instead.";
    }

    $("#w1_weight").addEventListener("input", (e) => {
      state.w1_weight = parseFloat(e.target.value);
      $("#w1_weight_val").textContent = fmt(state.w1_weight, 2);
      scheduleIndexFetch();
    });
    $("#pelt_penalty").addEventListener("input", (e) => {
      state.pelt_penalty = parseFloat(e.target.value);
      $("#pelt_penalty_val").textContent = fmt(state.pelt_penalty, 1);
      scheduleIndexFetch();
    });
    $("#momentum_window").addEventListener("input", (e) => {
      state.momentum_window = parseInt(e.target.value, 10);
      $("#momentum_window_val").textContent = state.momentum_window;
      scheduleIndexFetch();
    });
    $("#use_synthetic").addEventListener("change", (e) => {
      state.use_synthetic = e.target.checked;
      // Convergence view is synthetic-aware; force a reload next time it's shown
      // (and immediately, if it's the active tab) so it never shows stale mode.
      state.convergenceLoaded = false;
      scheduleIndexFetch();
      if ($("#tab-convergence").classList.contains("active")) loadConvergence();
    });
    $("#probe_budget").addEventListener("input", (e) => {
      $("#probe_budget_val").textContent = e.target.value;
    });
  }

  // -------------------------------------------------- Index Construction --
  // + Structural Breaks (both driven by the same /api/index payload)

  function renderIndexTabs(payload) {
    Charts.twoWave("chart-two-wave", payload.records, payload.breaks);
    Charts.momentum("chart-momentum", payload.records, payload.params.momentum_window);
    renderBreakStats(payload.breaks);
    renderBreaksTable(payload.breaks);
    Charts.singleSeries("chart-incumbent-top", payload.records.map((r) => r.date), payload.records.map((r) => r.market_rel_strength),
      "Fintech / legacy relative strength", Charts.cssVar("--wave1"), "Market relative strength", payload.breaks.series.wave1.break_dates);
    Charts.singleSeries("chart-incumbent-bottom", payload.records.map((r) => r.date), payload.records.map((r) => r.edgar_ai_intensity),
      "EDGAR AI-language intensity", Charts.cssVar("--wave2"), "EDGAR AI-language intensity (per filing)", payload.breaks.series.wave2.break_dates);
  }

  function renderBreakStats(breaks) {
    const labels = { wave1: "Wave 1", wave2: "Wave 2", FDI: "Composite FDI" };
    $("#break-stats").innerHTML = Object.entries(labels).map(([key, label]) => `
      <div class="stat-tile">
        <div class="stat-label">${label} breaks</div>
        <div class="stat-value">${breaks.series[key].n_breaks}</div>
        <div class="stat-sub">${breaks.series[key].break_dates.join(", ") || "none"}</div>
      </div>`).join("");
  }

  function stabilityLabel(pct) {
    if (pct >= 70) return { text: "robust", cls: "sig-yes" };
    if (pct >= 40) return { text: "moderate", cls: "" };
    return { text: "fragile", cls: "sig-no" };
  }

  function renderBreaksTable(breaks) {
    const labels = { wave1: "Wave 1", wave2: "Wave 2", FDI: "Composite FDI" };
    let rows = "";
    for (const [key, label] of Object.entries(labels)) {
      for (const tp of breaks.series[key].turning_points) {
        const s = stabilityLabel(tp.stability_pct);
        const dirClass = tp.direction === "acceleration" ? "sig-yes" : tp.direction === "slowdown" ? "sig-no" : "";
        rows += `<tr><td>${label}</td><td>${tp.break_date}</td><td class="${dirClass}">${tp.direction}</td>`
          + `<td>${fmt(tp.stability_pct, 1)}% (${tp.n_settings_matched}/${tp.n_settings})</td>`
          + `<td class="${s.cls}">${s.text}</td></tr>`;
      }
    }
    $("#table-breaks").innerHTML = rows
      ? `<table><thead><tr><th>Series</th><th>Turning point</th><th>Direction</th><th>Stability (across settings)</th><th>Verdict</th></tr></thead><tbody>${rows}</tbody></table>`
      : `<p class="tab-intro">No turning point detected at this penalty / window setting.</p>`;
  }

  // ------------------------------------------------------ Data Collection --

  async function loadDataCollection() {
    try {
      const data = await Api.dataCollection();
      state._dc = data;
      state.dataCollectionLoaded = true;
      renderDataCollection(data);
    } catch (e) {
      $("#tab-data-collection").insertAdjacentHTML("afterbegin", `<div class="synthetic-notice">${e.message}</div>`);
    }
  }

  function renderDataCollection(data) {
    Charts.indexedPerformance("chart-indexed-performance", data.indexed_performance, data.ticker_order);
    Charts.trendsComparison("chart-trends", data.trends_yearly);
    Charts.edgarYearly("chart-edgar-yearly", data.edgar_yearly);

    $("#table-edgar-2026").innerHTML = data.edgar_2026_agentic.length
      ? `<table><thead><tr><th>Ticker</th><th>Company</th><th>Category</th><th>Mentions</th></tr></thead><tbody>${
          data.edgar_2026_agentic.map((r) => `<tr><td>${r.ticker}</td><td>${r.name}</td><td>${r.category.replace("_", " ")}</td><td>${r.mentions}</td></tr>`).join("")
        }</tbody></table>`
      : `<p class="tab-intro">No 2026 filings mention "agentic" language yet.</p>`;

    // Drop any year with no real net-income data for any ticker: yfinance only
    // exposes ~4 fiscal years, so the earliest year (e.g. 2021) comes back all
    // null/missing. Showing it as an empty "—"/"n/a" column looks like missing
    // evidence when the source simply doesn't provide that year.
    const years = [...new Set(data.fundamentals.map((r) => r.fiscal_year))]
      .filter((y) => data.fundamentals.some((r) => r.fiscal_year === y && r.net_income !== null && r.net_income !== undefined))
      .sort();
    const byTicker = {};
    for (const r of data.fundamentals) {
      byTicker[r.ticker] = byTicker[r.ticker] || { name: r.name, values: {} };
      byTicker[r.ticker].values[r.fiscal_year] = r.net_income;
    }
    $("#table-fundamentals").innerHTML = `<table><thead><tr><th>Ticker</th>${years.map((y) => `<th>${y}</th>`).join("")}</tr></thead><tbody>${
      Object.entries(byTicker).map(([ticker, v]) => `<tr><td>${ticker}</td>${years.map((y) => `<td>${v.values[y] !== undefined ? fmtMoney(v.values[y]) : "—"}</td>`).join("")}</tr>`).join("")
    }</tbody></table>`;

    if (data.revenue_share && data.revenue_share.length) {
      Charts.revenueShare("chart-revenue-share", data.revenue_share);
    } else {
      $("#chart-revenue-share").innerHTML = `<p class="tab-intro">No revenue data available (re-run collect_market_data.py to populate the revenue column).</p>`;
    }
  }

  // --------------------------------------------------------- Robustness --

  async function loadRobustnessChecks() {
    try {
      const data = await Api.robustnessChecks();
      state._rc = data;
      state.robustnessChecksLoaded = true;
      renderRobustnessChecks(data);
    } catch (e) {
      $("#tab-robustness").insertAdjacentHTML("afterbegin", `<div class="synthetic-notice">${e.message}</div>`);
    }
  }

  function renderRobustnessChecks(data) {
    Charts.marketMarketwide("chart-mw-etf", "chart-mw-ratio", data.market_marketwide);
    Charts.edgarMarketwide("chart-edgar-mw-top", "chart-edgar-mw-bottom", data.edgar_marketwide);
    if (data.macro_control) Charts.macroControl("chart-macro-control", data.macro_control);
  }

  // ------------------------------------------------- Converging Evidence --

  async function loadConvergence() {
    try {
      const data = await Api.convergence({ synthetic: state.use_synthetic });
      state._conv = data;
      state.convergenceLoaded = true;
      renderConvergence(data);
    } catch (e) {
      $("#tab-convergence").insertAdjacentHTML("afterbegin", `<div class="synthetic-notice">${e.message}</div>`);
    }
  }

  function renderConvergence(data) {
    Charts.convergence("chart-convergence", data.records, data.signals);
    const w1 = data.signals.filter((s) => s.wave === "wave1").length;
    const w2 = data.signals.filter((s) => s.wave === "wave2").length;
    $("#convergence-caption").textContent =
      `${w1} Wave 1 signals (warm) and ${w2} Wave 2 signals (cool), each z-scored and smoothed. `
      + "No single line proves the thesis — the argument is that independent sources move together.";
    const waveLabel = { wave1: "Wave 1", wave2: "Wave 2" };
    const rows = data.signals.map((s) =>
      `<tr><td>${s.label}</td><td>${waveLabel[s.wave]}</td><td>${s.peak_date || "—"}</td></tr>`).join("");
    $("#table-convergence").innerHTML =
      `<table><thead><tr><th>Signal</th><th>Wave</th><th>Peaks (smoothed)</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function initRobustnessAgent() {
    $("#run-robustness").addEventListener("click", async () => {
      const apiKey = $("#gemini_api_key").value.trim();
      const statusEl = $("#robustness-status");
      const btn = $("#run-robustness");
      btn.disabled = true;
      statusEl.textContent = "Agent is probing the parameter space — this calls Gemini repeatedly and may take a minute or two…";
      $("#robustness-result").innerHTML = "";
      try {
        const result = await Api.robustnessRun({
          max_steps: parseInt($("#probe_budget").value, 10),
          synthetic: state.use_synthetic,
          api_key: apiKey || null,
        });
        renderRobustnessResult(result);
        statusEl.textContent = `${result.steps_used}/${result.max_steps} probes used` + (result.used_synthetic ? " · synthetic data" : "");
      } catch (e) {
        statusEl.textContent = `Robustness agent failed: ${e.message}`;
      } finally {
        btn.disabled = false;
      }
    });
  }

  function renderRobustnessResult(result) {
    const trace = result.trace.map((entry, i) => {
      const p = entry.params;
      const header = `<div class="probe-params"><b>Probe ${i + 1}</b> — w1_weight=${p.w1_weight}, pelt_penalty=${p.pelt_penalty}, momentum_window=${p.momentum_window}</div>`;
      if (entry.error) return `<div class="probe-entry">${header}<div class="probe-breaks">error: ${entry.error}</div></div>`;
      const cols = ["wave1", "wave2", "FDI"].map((k) => {
        const dates = entry.result[k].break_dates;
        return `${k}: ${dates.length ? dates.join(", ") : "none"}`;
      }).join(" &nbsp;·&nbsp; ");
      return `<div class="probe-entry">${header}<div class="probe-breaks">${cols}</div></div>`;
    }).join("");
    $("#robustness-result").innerHTML = `
      <details class="ai-key-details" open><summary>Probe trace (${result.trace.length} calls)</summary>${trace}</details>
      <div class="markdown-body">${marked.parse(result.verdict || "")}</div>`;
  }

  // --------------------------------------------------------------- Verdict --

  async function loadVerdict() {
    try {
      const data = await Api.verdict();
      state.verdictLoaded = true;
      $("#verdict-md").innerHTML = marked.parse(data.verdict_md || "");
      $("#findings-md").innerHTML = marked.parse(data.findings_md || "");
    } catch (e) {
      $("#verdict-md").innerHTML = `<p>${e.message}</p>`;
    }
  }

  function renderOverviewStats(payload) {
    const b = payload.breaks;
    const totalBreaks = b.series.wave1.n_breaks + b.series.wave2.n_breaks;
    $("#overview-stats").innerHTML = `
      <div class="stat-tile"><div class="stat-label">Mode</div><div class="stat-value">${payload.used_synthetic ? "Synthetic" : "Real"}</div><div class="stat-sub">data</div></div>
      <div class="stat-tile"><div class="stat-label">Wave 1 breaks</div><div class="stat-value">${b.series.wave1.n_breaks}</div><div class="stat-sub">${b.series.wave1.break_dates.join(", ") || "none"}</div></div>
      <div class="stat-tile"><div class="stat-label">Wave 2 breaks</div><div class="stat-value">${b.series.wave2.n_breaks}</div><div class="stat-sub">${b.series.wave2.break_dates.join(", ") || "none"}</div></div>
      <div class="stat-tile"><div class="stat-label">Composite FDI breaks</div><div class="stat-value">${b.series.FDI.n_breaks}</div><div class="stat-sub">${b.series.FDI.break_dates.join(", ") || "none"}</div></div>`;
  }

  // ----------------------------------------------------- AI assistant --

  function initAiAssistant() {
    $("#gen-summary").addEventListener("click", async () => {
      const btn = $("#gen-summary");
      const out = $("#ai-summary-output");
      btn.disabled = true;
      out.innerHTML = `<p class="tab-intro">Asking Gemini…</p>`;
      try {
        const apiKey = $("#gemini_api_key").value.trim();
        const res = await Api.aiSummary({ ...currentParams(), api_key: apiKey || null });
        out.innerHTML = marked.parse(res.summary || "");
      } catch (e) {
        out.innerHTML = `<p class="tab-intro">Gemini request failed: ${e.message}</p>`;
      } finally {
        btn.disabled = false;
      }
    });

    $("#chat-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = $("#chat-input");
      const question = input.value.trim();
      if (!question) return;
      input.value = "";
      appendChatMsg("user", question);
      state.chatHistory.push({ role: "user", content: question });
      appendChatMsg("assistant", "…thinking…", true);
      try {
        const apiKey = $("#gemini_api_key").value.trim();
        const res = await Api.aiChat({
          ...currentParams(), api_key: apiKey || null,
          question, history: state.chatHistory.slice(0, -1),
        });
        replaceLastAssistantMsg(res.answer);
        state.chatHistory.push({ role: "assistant", content: res.answer });
      } catch (err) {
        replaceLastAssistantMsg(`Gemini request failed: ${err.message}`);
      }
    });
  }

  function appendChatMsg(role, text, placeholder) {
    const div = document.createElement("div");
    div.className = `chat-msg ${role}`;
    if (placeholder) div.dataset.placeholder = "1";
    div.textContent = text;
    $("#chat-history").appendChild(div);
    $("#chat-history").scrollTop = $("#chat-history").scrollHeight;
  }
  function replaceLastAssistantMsg(text) {
    const placeholder = $("#chat-history").querySelector('[data-placeholder="1"]');
    if (placeholder) {
      placeholder.innerHTML = marked.parseInline ? marked.parse(text) : text;
      delete placeholder.dataset.placeholder;
    }
  }

  // ------------------------------------------------------------- init --

  async function init() {
    initTheme();
    initTabs();
    initRobustnessAgent();
    initAiAssistant();
    const status = await Api.status();
    initSidebar(status);
    await fetchIndex();
    await loadDataCollection(); // default active tab
  }

  document.addEventListener("DOMContentLoaded", init);
})();
