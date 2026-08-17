class App {
  constructor() {
    this.sessionId = "memory:demo-user";
    this.currentSessionId = this.sessionId;
    this.selectedNode = null;
    this.currentView = window.location.hash.startsWith("#studio") ? "studio" : "landing";
    this.graphVisualizer = new GraphVisualizer("studioGraphCanvas");
    window.graphVisualizer = this.graphVisualizer;
    this.healthMonitor = new HealthMonitor();
    this.timelineController = new TimelineController();
    this.applyTheme(localStorage.getItem("echotrace_theme") || "dark");
    this.bindControls();
    this.initializeScrollStory();
    this.showView(this.currentView, false);
    this.checkHealth();
    if (this.currentView === "studio") this.openStudio();
  }

  bindControls() {
    document.getElementById("btnLaunchStudio")?.addEventListener("click", () => {
      if (this.currentView === "studio") this.showView("landing");
      else this.openStudio();
    });
    document.getElementById("heroLaunchButton")?.addEventListener("click", () => this.openStudio());
    document.getElementById("btnViewLiveGraph")?.addEventListener("click", () => this.openStudio());
    ["btnBackOverview", "brandButton"].forEach((id) => {
      document.getElementById(id)?.addEventListener("click", () => this.showView("landing"));
    });
    window.addEventListener("hashchange", () => {
      const view = window.location.hash.startsWith("#studio") ? "studio" : "landing";
      if (view !== this.currentView) this.showView(view, false);
    });

    document.getElementById("btnThemeToggle")?.addEventListener("click", () => {
      const theme = document.documentElement.classList.contains("theme-light") ? "dark" : "light";
      this.applyTheme(theme);
      localStorage.setItem("echotrace_theme", theme);
    });
    document.getElementById("demoChatForm")?.addEventListener("submit", (event) => this.submitChat(event));
    document.getElementById("btnNewChat")?.addEventListener("click", () => this.newChat());
    document.getElementById("chatThread")?.addEventListener("click", (event) => {
      const chip = event.target.closest("[data-suggestion]");
      if (chip) {
        document.getElementById("demoChatInput").value = chip.getAttribute("data-suggestion");
        this.submitChat(new Event("submit"));
      }
    });
  }

  initializeScrollStory() {
    const progress = document.getElementById("scrollProgressBar");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const revealElements = document.querySelectorAll("[data-reveal]");

    if (reducedMotion || !("IntersectionObserver" in window)) {
      revealElements.forEach((element) => element.classList.add("is-revealed"));
    } else {
      document.documentElement.classList.add("motion-ready");
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          entry.target.classList.toggle("is-revealed", entry.isIntersecting);
        });
      }, { rootMargin: "-8% 0px -8% 0px", threshold: 0.12 });
      revealElements.forEach((element) => observer.observe(element));
    }

    const updateProgress = () => {
      if (!progress || this.currentView !== "landing") return;
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      const percent = scrollable > 0 ? Math.min(100, (window.scrollY / scrollable) * 100) : 0;
      progress.style.width = `${percent}%`;
    };
    window.addEventListener("scroll", updateProgress, { passive: true });
    window.addEventListener("resize", updateProgress);
    updateProgress();
  }

  async openStudio() {
    this.showView("studio", false);
    const url = new URL(window.location.href);
    url.hash = "studio";
    window.history.replaceState({}, "", url);
    this.populateSuggestions();
    await this.refreshStudio();
  }

  showView(view, updateLocation = true) {
    this.currentView = view;
    const landing = document.getElementById("landingView");
    const studio = document.getElementById("studioView");
    const nav = document.getElementById("landingNav");
    const footer = document.getElementById("siteFooter");
    const label = document.getElementById("launchLabel");
    if (view === "studio") {
      landing?.classList.add("hidden");
      studio?.classList.remove("hidden");
      studio?.classList.add("flex");
      nav?.classList.add("invisible");
      footer?.classList.add("hidden");
      document.getElementById("scrollProgressBar")?.classList.add("hidden");
      if (label) label.textContent = "Overview";
      if (updateLocation) window.location.hash = "studio";
      requestAnimationFrame(() => { this.graphVisualizer.resizeCanvas(); this.refreshStudio(); });
    } else {
      studio?.classList.add("hidden");
      studio?.classList.remove("flex");
      landing?.classList.remove("hidden");
      nav?.classList.remove("invisible");
      footer?.classList.remove("hidden");
      document.getElementById("scrollProgressBar")?.classList.remove("hidden");
      if (label) label.textContent = "Launch App";
      if (updateLocation) window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}`);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  applyTheme(theme) {
    document.documentElement.classList.toggle("theme-light", theme === "light");
    document.documentElement.classList.toggle("dark", theme !== "light");
    const icon = document.getElementById("themeIcon");
    if (icon) icon.textContent = theme === "light" ? "dark_mode" : "light_mode";
    this.graphVisualizer?.draw();
  }

  async checkHealth() {
    const status = document.getElementById("engineStatus");
    if (!status) return;
    try {
      const health = await API.getHealth();
      status.textContent = health.engine_mode.toUpperCase();
      status.className = health.hydradb_connected ? "hidden font-mono text-[10px] text-status-healthy sm:inline" : "hidden font-mono text-[10px] text-status-warning sm:inline";
    } catch (error) {
      status.textContent = "BACKEND OFFLINE";
      status.className = "hidden font-mono text-[10px] text-status-warning sm:inline";
    }
  }

  async refreshStudio() {
    if (this.currentView !== "studio") return;
    try {
      const graph = await API.getGraph(this.sessionId);
      this.graphVisualizer.setData(graph.nodes || [], graph.edges || []);
      const empty = document.getElementById("emptyGraphState");
      if (empty) {
        empty.classList.toggle("hidden", graph.nodes.length > 0);
        empty.classList.toggle("grid", graph.nodes.length === 0);
      }
      const counts = document.getElementById("demoCountsBadge");
      if (counts) counts.textContent = `${graph.nodes.length} nodes · ${graph.edges.length} edges`;
      await this.healthMonitor.fetchAndRender(this.sessionId);
      const times = graph.nodes.map((node) => Date.parse(node.valid_from)).filter(Number.isFinite);
      if (times.length) this.timelineController.setRange(new Date(Math.min(...times)).toISOString(), new Date().toISOString());
      this.graphVisualizer.resizeCanvas();
    } catch (error) {
      this.message(`Session load failed: ${error.message}`, true);
    }
  }

  populateSuggestions() {
    const container = document.getElementById("suggestionChips");
    if (!container) return;
    const suggestions = [
      "My trip is in June.",
      "When is my trip?",
      "Plan my trip itinerary.",
      "Where did I go to university?",
    ];
    container.innerHTML = "";
    suggestions.forEach((text) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.setAttribute("data-suggestion", text);
      chip.className = "rounded-full border border-border-subtle bg-surface-elevated px-3 py-1.5 font-mono text-[11px] text-text-secondary transition-colors hover:border-vermilion/60 hover:text-text-primary";
      chip.textContent = text;
      container.appendChild(chip);
    });
  }

  appendChatBubble(role, html, meta) {
    const thread = document.getElementById("chatThread");
    if (!thread) return;
    const empty = thread.querySelector(".chat-empty");
    if (empty) empty.remove();
    const bubble = document.createElement("div");
    bubble.className = role === "user"
      ? "max-w-[85%] self-end rounded-2xl rounded-br-sm bg-vermilion px-3.5 py-2.5 text-sm text-white"
      : "max-w-[92%] self-start rounded-2xl rounded-bl-sm border border-border-subtle bg-surface-elevated px-3.5 py-2.5 text-sm text-text-primary";
    bubble.innerHTML = html;
    if (meta) {
      const tag = document.createElement("div");
      tag.className = `mt-1.5 font-mono text-[10px] ${role === "user" ? "text-white/70" : "text-text-muted"}`;
      tag.textContent = meta;
      bubble.appendChild(tag);
    }
    thread.appendChild(bubble);
    thread.scrollTop = thread.scrollHeight;
  }

  renderMarkdown(text) {
    const escaped = this.escapeHtml(text);
    return escaped
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`(.+?)`/g, "<code class=\"rounded bg-bg-canvas px-1 py-0.5 font-mono text-[0.85em] text-status-healthy\">$1</code>")
      .replace(/\n/g, "<br />");
  }

  newChat() {
    const thread = document.getElementById("chatThread");
    if (thread) thread.innerHTML = '<div class="chat-empty">Talk to EchoTrace like a real agent. Each message becomes a new session, commits to HydraDB, and connects the graph live.</div>';
    document.getElementById("demoChatInput")?.focus();
  }

  async submitChat(event) {
    event.preventDefault();
    const input = document.getElementById("demoChatInput");
    const button = document.getElementById("btnSendDemoMessage");
    const content = input.value.trim();
    if (!content) return;
    this.setBusy(button, true, "");
    this.appendChatBubble("user", this.escapeHtml(content));
    input.value = "";
    this.setDemoWriteState("WRITING");
    try {
      const result = await API.sendDemoMessage(content);
      this.currentSessionId = result.session_id;
      const badge = document.getElementById("demoSessionBadge");
      if (badge) badge.textContent = result.session_id;
      if (result.reached_cap) {
        this.appendChatBubble("assistant", this.renderMarkdown(result.assistant_reply));
        this.setDemoWriteState("COMMITTED", result.engine_mode);
        return;
      }
      const meta = `session ${result.session_id} · committed to HydraDB · ${result.node_count} nodes · ${result.edge_count} edges`;
      this.appendChatBubble("assistant", this.renderMarkdown(result.assistant_reply), meta);
      this.setDemoWriteState("COMMITTED", result.engine_mode);
      await this.refreshStudio();
    } catch (error) {
      this.setDemoWriteState("FAILED");
      this.appendChatBubble("assistant", this.escapeHtml(`Error: ${error.message}`));
    } finally {
      this.setBusy(button, false, "");
    }
  }

  inspectNode(node) {
    this.selectedNode = node;
  }

  setDemoWriteState(state, engineMode = "HYDRADB BOLT") {
    const indicator = document.getElementById("demoWriteIndicator");
    const engine = document.getElementById("demoEngineMode");
    if (indicator) {
      indicator.textContent = state;
      const successful = state === "COMMITTED";
      const failed = state === "FAILED";
      indicator.className = `text-[10px] ${successful ? "text-status-healthy" : failed ? "text-status-warning" : "text-text-muted"}`;
    }
    if (engine) engine.textContent = engineMode.toUpperCase();
  }

  setBusy(button, busy, label) {
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle("opacity-60", busy);
    const text = Array.from(button.childNodes).find((node) => node.nodeType === Node.TEXT_NODE);
    if (text) text.textContent = label;
  }

  escapeHtml(value) {
    const element = document.createElement("span");
    element.textContent = String(value ?? "");
    return element.innerHTML;
  }

  message(text, isError = false) {
    const element = document.getElementById("operationMessage");
    if (!element) return;
    element.textContent = text;
    element.className = `rounded border px-4 py-3 font-mono text-sm ${isError ? "border-status-warning/50 bg-status-warning/10 text-status-warning" : "border-status-healthy/50 bg-status-healthy/10 text-status-healthy"}`;
    element.classList.remove("hidden");
  }
}

window.addEventListener("DOMContentLoaded", () => { window.app = new App(); });