/* charts.js -- Plotly chart builders. All colors are read from the CSS
   custom properties in style.css (the validated dataviz palette), so charts
   follow the light/dark theme automatically -- re-call the render function
   after a theme switch to pick up new values. */

const Charts = (() => {
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  const TICKER_COLOR_ORDER = [
    cssVarLazy("--series-blue"), cssVarLazy("--series-green"), cssVarLazy("--series-magenta"),
    cssVarLazy("--series-yellow"), cssVarLazy("--series-aqua"), cssVarLazy("--series-orange"),
    cssVarLazy("--series-violet"), cssVarLazy("--series-red"),
  ];
  // lazily evaluated at call time so the theme's current values are used,
  // not whatever was set on first script parse
  function cssVarLazy(name) { return () => cssVar(name); }
  function tickerColor(i) { return TICKER_COLOR_ORDER[i % TICKER_COLOR_ORDER.length](); }

  function baseLayout(extra) {
    return Object.assign({
      paper_bgcolor: cssVar("--surface-1"),
      plot_bgcolor: cssVar("--surface-1"),
      font: { color: cssVar("--text-primary"), family: "system-ui, -apple-system, Segoe UI, sans-serif", size: 12 },
      margin: { l: 55, r: 20, t: 10, b: 40 },
      hovermode: "x unified",
      legend: { orientation: "h", y: 1.12, x: 0, font: { size: 11 } },
      xaxis: { gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline"), linecolor: cssVar("--baseline") },
      yaxis: { gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline"), linecolor: cssVar("--baseline") },
    }, extra || {});
  }

  // Modebar pared down to just zoom in/out + download -- pan, box-zoom,
  // autoscale, and reset-axes removed as visual clutter most readers never use.
  const config = {
    responsive: true, displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "zoom2d", "pan2d", "autoScale2d", "resetScale2d"],
  };

  function breakShapes(breakDates, color) {
    return (breakDates || []).map((d) => ({
      type: "line", x0: d, x1: d, yref: "paper", y0: 0, y1: 1,
      line: { color, width: 1.2, dash: "dash" }, opacity: 0.7,
    }));
  }
  function breakAnnotations(breakDates, color, label) {
    return (breakDates || []).map((d) => ({
      x: d, yref: "paper", y: 1, showarrow: false, text: `${label}<br>${d.slice(0, 7)}`,
      font: { size: 9, color }, xanchor: "left", yanchor: "bottom",
    }));
  }

  function twoWave(divId, records, breaks) {
    const x = records.map((r) => r.date);
    const wave1 = records.map((r) => r.wave1);
    const wave2 = records.map((r) => r.wave2);
    const fdi = records.map((r) => r.FDI);

    const traces = [
      { x, y: wave1, name: "Wave 1 (payments / neobanks)", type: "scatter", mode: "lines", line: { color: cssVar("--wave1"), width: 2.2 } },
      { x, y: wave2, name: "Wave 2 (AI-native finance)", type: "scatter", mode: "lines", line: { color: cssVar("--wave2"), width: 2.2 } },
      { x, y: fdi, name: "Composite FDI", type: "scatter", mode: "lines", line: { color: cssVar("--fdi"), width: 1.6, dash: "dot" } },
    ];

    const shapes = [
      ...breakShapes(breaks.series.wave1.break_dates, cssVar("--wave1")),
      ...breakShapes(breaks.series.wave2.break_dates, cssVar("--wave2")),
    ];
    const annotations = [
      ...breakAnnotations(breaks.series.wave1.break_dates, cssVar("--wave1"), "W1 break"),
      ...breakAnnotations(breaks.series.wave2.break_dates, cssVar("--wave2"), "W2 break"),
    ];

    Plotly.react(divId, traces, baseLayout({
      shapes, annotations,
      yaxis: { title: "Standardised index (z-score)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") },
    }), config);
  }

  function momentum(divId, records, window) {
    const x = records.map((r) => r.date);
    const w1 = records.map((r) => r.wave1);
    const w2 = records.map((r) => r.wave2);
    const diffN = (arr) => arr.map((v, i) => (i < window ? null : v - arr[i - window]));
    const m1 = diffN(w1), m2 = diffN(w2);

    const traces = [
      { x, y: m1, name: `Wave 1 momentum (${window}m)`, type: "scatter", mode: "lines", line: { color: cssVar("--wave1"), width: 2.2 }, fill: "tozeroy", fillcolor: "rgba(227,73,72,0.08)" },
      { x, y: m2, name: `Wave 2 momentum (${window}m)`, type: "scatter", mode: "lines", line: { color: cssVar("--wave2"), width: 2.2 } },
    ];
    Plotly.react(divId, traces, baseLayout({
      yaxis: { title: `${window}-month change in sub-index`, gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") },
      shapes: [{ type: "line", x0: x[0], x1: x[x.length - 1], y0: 0, y1: 0, line: { color: cssVar("--baseline"), width: 1 } }],
    }), config);
  }

  function singleSeries(divId, x, y, name, color, yTitle, breakDates) {
    const shapes = breakShapes(breakDates, color);
    Plotly.react(divId, [{ x, y, name, type: "scatter", mode: "lines", line: { color, width: 2.2 }, showlegend: false }],
      // hovermode "closest" instead of baseLayout's default "x unified": with
      // only one trace, the unified hover box adds nothing and just floats a
      // white box over the line, visually covering part of the chart.
      baseLayout({ shapes, hovermode: "closest", yaxis: { title: yTitle, gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") }, legend: { y: -0.2 } }), config);
  }

  function indexedPerformance(divId, records, tickerOrder) {
    const byTicker = {};
    for (const r of records) {
      (byTicker[r.ticker] = byTicker[r.ticker] || []).push(r);
    }
    const traces = tickerOrder.filter((t) => byTicker[t]).map((t, i) => {
      const rows = byTicker[t];
      return {
        x: rows.map((r) => r.date), y: rows.map((r) => r.value),
        name: `${t} — ${rows[0].name}`, type: "scatter", mode: "lines",
        line: { color: tickerColor(i), width: 2 },
      };
    });
    traces.push({
      x: [records[0].date, records[records.length - 1].date], y: [100, 100],
      name: "start (100)", type: "scatter", mode: "lines",
      line: { color: cssVar("--baseline"), width: 1, dash: "dash" }, showlegend: false, hoverinfo: "skip",
    });
    Plotly.react(divId, traces, baseLayout({
      yaxis: { title: "Indexed price (start = 100)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") },
      legend: { orientation: "h", y: 1.22, x: 0, font: { size: 10 } },
      margin: { l: 55, r: 20, t: 10, b: 40 },
    }), config);
  }

  function trendsComparison(divId, records) {
    const byWaveYear = {};
    for (const r of records) {
      const key = `${r.wave}|${r.year}`;
      (byWaveYear[key] = byWaveYear[key] || []).push(r.interest);
    }
    const years = [...new Set(records.map((r) => r.year))].sort();
    const avg = (wave) => years.map((y) => {
      const vals = byWaveYear[`${wave}|${y}`] || [];
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    });
    const traces = [
      { x: years, y: avg("wave1"), name: "Wave 1 terms", type: "scatter", mode: "lines+markers", line: { color: cssVar("--wave1"), width: 2.2 }, marker: { size: 8 } },
      { x: years, y: avg("wave2"), name: "Wave 2 terms", type: "scatter", mode: "lines+markers", line: { color: cssVar("--wave2"), width: 2.2 }, marker: { size: 8 } },
    ];
    Plotly.react(divId, traces, baseLayout({
      yaxis: { title: "Avg. relative interest (0-100)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") },
      xaxis: { title: "Year", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline"), dtick: 1 },
    }), config);
  }

  function edgarYearly(divId, records) {
    const years = [...new Set(records.map((r) => r.year))].sort();
    const byQuery = (q) => years.map((y) => {
      const row = records.find((r) => r.year === y && r.query === q);
      return row ? row.mentions : 0;
    });
    const traces = [
      { x: years, y: byQuery("agentic"), name: '"agentic"', type: "bar", marker: { color: cssVar("--wave2") } },
      { x: years, y: byQuery("ai_broad"), name: '"artificial intelligence"', type: "bar", marker: { color: cssVar("--series-violet") } },
    ];
    Plotly.react(divId, traces, baseLayout({
      barmode: "group",
      yaxis: { title: "Filings mentioning term", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") },
      xaxis: { title: "Year", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline"), dtick: 1 },
    }), config);
  }

  function marketMarketwide(topDivId, bottomDivId, data) {
    const finx = data.etf_indexed.filter((r) => r.ticker === "FINX");
    const kbwb = data.etf_indexed.filter((r) => r.ticker === "KBWB");
    Plotly.react(topDivId, [
      { x: finx.map((r) => r.date), y: finx.map((r) => r.value), name: finx[0] ? `${finx[0].name} (FINX)` : "FINX", type: "scatter", mode: "lines", line: { color: cssVar("--series-aqua"), width: 2.2 } },
      { x: kbwb.map((r) => r.date), y: kbwb.map((r) => r.value), name: kbwb[0] ? `${kbwb[0].name} (KBWB)` : "KBWB", type: "scatter", mode: "lines", line: { color: cssVar("--series-blue"), width: 2.2 } },
    ], baseLayout({ yaxis: { title: "Indexed price (start = 100)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") } }), config);

    Plotly.react(bottomDivId, [
      { x: data.sample_ratio.map((r) => r.date), y: data.sample_ratio.map((r) => r.value), name: "7-ticker sample (fintech / legacy)", type: "scatter", mode: "lines", line: { color: cssVar("--wave1"), width: 2.2 } },
      { x: data.etf_ratio.map((r) => r.date), y: data.etf_ratio.map((r) => r.value), name: "Sector ETFs (FINX / KBWB)", type: "scatter", mode: "lines", line: { color: cssVar("--series-violet"), width: 2.2, dash: "dash" } },
    ], baseLayout({ yaxis: { title: "Relative strength (rebased to 100)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") } }), config);
  }

  function edgarMarketwide(topDivId, bottomDivId, data) {
    // Both single-trace -- "closest" avoids an unnecessary floating hover box.
    Plotly.react(topDivId, [
      { x: data.marketwide_agentic.map((r) => r.year), y: data.marketwide_agentic.map((r) => r.total_filings), name: "Market-wide", type: "bar", marker: { color: cssVar("--series-violet") }, showlegend: false },
    ], baseLayout({ hovermode: "closest", yaxis: { title: "Market-wide 10-K filings\n(all SEC filers)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") }, xaxis: { title: "", gridcolor: cssVar("--gridline"), dtick: 1 } }), config);

    Plotly.react(bottomDivId, [
      { x: data.sample_agentic.map((r) => r.year), y: data.sample_agentic.map((r) => r.mentions), name: "7-company sample", type: "bar", marker: { color: cssVar("--wave1") }, showlegend: false },
    ], baseLayout({ hovermode: "closest", yaxis: { title: "7-company sample\n(mentions)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") }, xaxis: { title: "Year", gridcolor: cssVar("--gridline"), dtick: 1 } }), config);
  }

  function revenueShare(divId, rows) {
    const years = rows.map((r) => r.fiscal_year);
    const share = rows.map((r) => r.fintech_share_pct);
    const traces = [{
      x: years, y: share, type: "bar",
      marker: { color: cssVar("--wave1") },
      text: share.map((v) => `${v.toFixed(1)}%`), textposition: "outside",
      hovertemplate: "%{x}: %{y:.1f}% of pool<extra></extra>", showlegend: false,
    }];
    Plotly.react(divId, traces, baseLayout({
      // single trace -- "closest" instead of baseLayout's default "x unified"
      // avoids floating an unnecessary hover box over the bars.
      hovermode: "closest",
      // y starts at 0 on purpose: a zoomed axis would exaggerate a ~1pt move
      // into a dramatic climb. Honest framing -- the share barely moved.
      yaxis: { title: "Fintech share of revenue pool (%)", range: [0, Math.max(30, Math.max(...share) * 1.25)], gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") },
      xaxis: { title: "Fiscal year", dtick: 1, gridcolor: cssVar("--gridline") },
    }), config);
  }

  function macroControl(divId, data) {
    const line = (recs) => ({ x: recs.map((r) => r.date), y: recs.map((r) => r.value) });
    const traces = [
      { ...line(data.sample_ratio_vs_legacy), name: "vs. banks (JPM/HSBC/BCS)", type: "scatter", mode: "lines", line: { color: cssVar("--wave1"), width: 2.4 } },
    ];
    const benchColors = { QQQ: cssVar("--series-violet"), ARKK: cssVar("--series-aqua") };
    const benchLabel = { QQQ: "vs. QQQ (Nasdaq-100 growth)", ARKK: "vs. ARKK (speculative growth)" };
    for (const b of ["QQQ", "ARKK"]) {
      if (data.vs_benchmark[b]) {
        traces.push({ ...line(data.vs_benchmark[b]), name: benchLabel[b], type: "scatter", mode: "lines", line: { color: benchColors[b], width: 2, dash: "dash" } });
      }
    }
    Plotly.react(divId, traces, baseLayout({
      yaxis: { title: "Fintech relative strength (start = 100)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 100, y1: 100, line: { color: cssVar("--baseline"), width: 1, dash: "dot" } }],
      annotations: [{ xref: "paper", x: 0.01, y: 100, yanchor: "bottom", text: "100 = fintech keeps pace", showarrow: false, font: { size: 10, color: cssVar("--text-muted") } }],
    }), config);
  }

  // Warm hues for Wave 1 signals, cool for Wave 2 -- so the two groups read as
  // two groups at a glance, which is the whole point of the convergence view.
  const CONVERGENCE_COLORS = {
    wave1: ["--wave1", "--series-orange", "--series-yellow"],
    wave2: ["--series-blue", "--series-aqua"],
  };

  function convergence(divId, records, signals) {
    const x = records.map((r) => r.date);
    const used = { wave1: 0, wave2: 0 };
    const traces = signals.map((s) => {
      const pool = CONVERGENCE_COLORS[s.wave] || CONVERGENCE_COLORS.wave1;
      const color = cssVar(pool[used[s.wave]++ % pool.length]);
      return {
        x, y: records.map((r) => r[s.key]), name: s.label,
        type: "scatter", mode: "lines",
        line: { color, width: 2.2, dash: s.wave === "wave2" ? "solid" : "solid" },
      };
    });
    Plotly.react(divId, traces, baseLayout({
      yaxis: { title: "Standardised signal (z-score, smoothed)", gridcolor: cssVar("--gridline"), zerolinecolor: cssVar("--baseline") },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0, y1: 0, line: { color: cssVar("--baseline"), width: 1 } }],
      legend: { orientation: "h", y: 1.16, x: 0, font: { size: 10 } },
    }), config);
  }

  return {
    twoWave, momentum, singleSeries, indexedPerformance, trendsComparison,
    edgarYearly, marketMarketwide, edgarMarketwide,
    revenueShare, macroControl, convergence, cssVar,
  };
})();
