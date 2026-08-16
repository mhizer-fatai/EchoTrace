/**
 * EchoTrace REST API Client
 */
const API = {
  baseUrl: '',

  async getHealth() {
    const res = await fetch(`${this.baseUrl}/api/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getGraph(sessionId = 'default', snapshotTime = null) {
    let url = `${this.baseUrl}/api/graph/${sessionId}`;
    if (snapshotTime) {
      url += `?snapshot_time=${encodeURIComponent(snapshotTime)}`;
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getBlastRadius(sessionId, factId) {
    const res = await fetch(`${this.baseUrl}/api/blast-radius/${sessionId}/${factId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async invalidateFact(sessionId, payload) {
    // Support either (sessionId, payload) or (payload, sessionId)
    let sId = sessionId;
    let data = payload;
    if (typeof sessionId === 'object' && payload === undefined) {
      data = sessionId;
      sId = 'default';
    }
    const res = await fetch(`${this.baseUrl}/api/facts/invalidate?session_id=${sId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return await res.json();
  },

  async healSubgraph(sessionId = 'default') {
    const res = await fetch(`${this.baseUrl}/api/subgraph/heal?session_id=${sessionId}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getMemoryHealth(sessionId = 'default') {
    const res = await fetch(`${this.baseUrl}/api/memory-health/${sessionId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async loadTrackThreeDemo() {
    const res = await fetch(`${this.baseUrl}/api/demo/track-three`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }
};

window.API = API;
window.apiClient = API;
