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

  // POST a body and consume a text/event-stream response, invoking
  // onEvent(eventName, dataObject) for each SSE frame. Pre-flight failures
  // (bad key, context build) come back as a normal non-2xx JSON error and are
  // thrown before any streaming begins; failures mid-stream arrive as an
  // {event: "error"} frame the caller handles like any other event.
  async function stream(path, body, onEvent) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `${res.status} ${res.statusText}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let sep;
      // SSE frames are separated by a blank line.
      while ((sep = buf.indexOf("\n\n")) >= 0) {
        const frame = buf.slice(0, sep);
        buf = buf.slice(sep + 2);
        let event = "message";
        let data = "";
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (data) onEvent(event, JSON.parse(data));
      }
    }
  }

  return {
    status: () => get("/api/status"),
    index: (params) => get("/api/index", params),
    dataCollection: () => get("/api/data-collection"),
    edgarStance: () => get("/api/edgar-stance"),
    robustnessChecks: () => get("/api/robustness-checks"),
    convergence: (params) => get("/api/convergence", params),
    verdict: () => get("/api/verdict"),
    aiSummaryStream: (body, onEvent) => stream("/api/ai/summary", body, onEvent),
    aiChatStream: (body, onEvent) => stream("/api/ai/chat", body, onEvent),
    robustnessAgent: (body) => post("/api/robustness-agent", body),
  };
})();
