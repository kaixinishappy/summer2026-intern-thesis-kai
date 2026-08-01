/* api.js -- thin fetch wrappers for the FastAPI backend in server.py. */

const Api = (() => {
  async function get(path, params) {
    const url = new URL(path, window.location.origin);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) url.searchParams.set(k, v);
      }
    }
    const res = await fetch(url);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `${res.status} ${res.statusText}`);
    }
    return res.json();
  }

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `${res.status} ${res.statusText}`);
    }
    return res.json();
  }

  return {
    status: () => get("/api/status"),
    index: (params) => get("/api/index", params),
    dataCollection: () => get("/api/data-collection"),
    edgarStance: () => get("/api/edgar-stance"),
    robustnessChecks: () => get("/api/robustness-checks"),
    convergence: (params) => get("/api/convergence", params),
    verdict: () => get("/api/verdict"),
    aiSummary: (body) => post("/api/ai/summary", body),
    aiChat: (body) => post("/api/ai/chat", body),
    robustnessAgent: (body) => post("/api/robustness-agent", body),
  };
})();
