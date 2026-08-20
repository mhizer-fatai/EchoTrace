class App {
  constructor() {
    this.guidedDemoSteps = [
      "My trip is in June.",
      "I work at Vertex Labs.",
      "I moved my trip to October.",
      "When is my trip?",
      "Which workplace was active when my trip was in October?",
      "Which university did I visit?",
      "Plan my trip itinerary.",
      "I moved my trip to November.",
    ];
    this.guidedCompletedSteps = new Set();
    this.sessionId = "memory:studio-user";
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
    this.healthPoll = window.setInterval(() => this.checkHealth(), 10000);
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
    document.getElementById("studioChatForm")?.addEventListener("submit", (event) => this.submitChat(event));
    document.getElementById("btnNewChat")?.addEventListener("click", () => this.newChat());
    document.getElementById("suggestionChips")?.addEventListener("click", (event) => {
      const chip = event.target.closest("[data-suggestion]");
      if (chip) {
        document.getElementById("studioChatInput").value = chip.getAttribute("data-suggestion");
        this.submitChat(new Event("submit"));
      }
    });
    document.getElementById("healAction")?.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-heal-studio]");
      if (!button) return;
      button.disabled = true;
      button.textContent = "UPDATING PLAN...";
      try {
        const result = await API.healStudioPlan();
        this.appendChatBubble("assistant", this.renderMarkdown(result.assistant_reply));
        await this.refreshStudio();
      } catch (error) {
        this.message(`Auto-heal failed: ${error.message}`, true);
        button.disabled = false;
        button.textContent = "AUTO-HEAL PLAN";
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
      const banner = document.getElementById("storeDegradedBanner");
      if (banner) {
        if (health.hydradb_degraded) {
          const reason = health.hydradb_degraded_reason || "HydraDB query health checks failed.";
          banner.textContent = `HydraDB store degraded: ${reason} EchoTrace is using its internal graph engine so the session remains usable. Run scripts/reset_store.ps1 (Windows) or scripts/reset_store.sh to restore HydraDB.`;
          banner.classList.remove("hidden");
        } else {
          banner.classList.add("hidden");
        }
      }
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
      const counts = document.getElementById("studioCountsBadge");
      if (counts) counts.textContent = `${graph.nodes.length} nodes · ${graph.edges.length} edges`;
      this.populateSuggestions(graph.nodes || []);
      this.updateHealAction(graph.nodes || []);
      await this.healthMonitor.fetchAndRender(this.sessionId);
      const times = graph.nodes.map((node) => Date.parse(node.valid_from)).filter(Number.isFinite);
      if (times.length) this.timelineController.setRange(new Date(Math.min(...times)).toISOString(), new Date().toISOString());
      this.graphVisualizer.resizeCanvas();
    } catch (error) {
      this.message(`Session load failed: ${error.message}`, true);
    }
  }

  populateSuggestions(nodes = []) {
    const container = document.getElementById("suggestionChips");
    if (!container) return;
    const recordedMessages = new Set(
      nodes
        .filter((node) => node.kind === "MESSAGE")
        .map((node) => String(node.content || "").trim().toLowerCase()),
    );
    this.guidedCompletedSteps.forEach((step) => recordedMessages.add(step));
    const nextSuggestion = this.guidedDemoSteps.find(
      (step) => !recordedMessages.has(step.toLowerCase()),
    );
    container.innerHTML = "";
    if (!nextSuggestion) {
      const done = document.createElement("span");
      done.className = "font-mono text-[11px] text-status-healthy";
      done.textContent = "DEMO FLOW COMPLETE";
      container.appendChild(done);
      return;
    }

    const label = document.createElement("span");
    label.className = "w-full font-mono text-[10px] text-text-muted";
    label.textContent = "NEXT DEMO STEP";
    container.appendChild(label);

    const chip = document.createElement("button");
    chip.type = "button";
    chip.setAttribute("data-suggestion", nextSuggestion);
    chip.className = "w-full rounded border border-vermilion/50 bg-vermilion/10 px-3 py-2 text-left font-mono text-[11px] text-text-primary transition-colors hover:border-vermilion hover:bg-vermilion/20";
    chip.textContent = nextSuggestion;
    container.appendChild(chip);
  }

  updateHealAction(nodes = []) {
    const container = document.getElementById("healAction");
    if (!container) return;
    const stale = nodes.filter((node) => node.is_stale && ["DECISION", "ARTIFACT"].includes(node.kind));
    container.innerHTML = "";
    if (!stale.length) {
      container.classList.add("hidden");
      return;
    }
    container.classList.remove("hidden");
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("data-heal-studio", "true");
    button.className = "w-full rounded border border-status-warning/60 bg-status-warning/10 px-3 py-2 font-mono text-[11px] font-bold text-status-warning hover:bg-status-warning/20";
    button.textContent = `AUTO-HEAL PLAN (${stale.length} outdated item${stale.length === 1 ? "" : "s"})`;
    container.appendChild(button);
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
    document.getElementById("studioChatInput")?.focus();
  }

  async submitChat(event) {
    event.preventDefault();
    const input = document.getElementById("studioChatInput");
    const button = document.getElementById("btnSendStudioMessage");
    const content = input.value.trim();
    if (!content) return;
    this.setBusy(button, true, "");
    this.appendChatBubble("user", this.escapeHtml(content));
    input.value = "";
    this.setStudioWriteState("WRITING");
    try {
      const result = await API.sendStudioMessage(content);
      this.guidedCompletedSteps.add(content.toLowerCase());
      this.currentSessionId = result.session_id;
      const badge = document.getElementById("studioSessionBadge");
      if (badge) badge.textContent = result.session_id;
      if (result.reached_cap) {
        this.appendChatBubble("assistant", this.renderMarkdown(result.assistant_reply));
        this.setStudioWriteState("COMMITTED", result.engine_mode);
        return;
      }
      const meta = `session ${result.session_id} · committed to HydraDB · ${result.node_count} nodes · ${result.edge_count} edges`;
      this.appendChatBubble("assistant", this.renderMarkdown(result.assistant_reply), meta);
      this.setStudioWriteState("COMMITTED", result.engine_mode);
      await this.refreshStudio();
    } catch (error) {
      this.setStudioWriteState("FAILED");
      this.appendChatBubble("assistant", this.escapeHtml(`Error: ${error.message}`));
    } finally {
      this.setBusy(button, false, "");
    }
  }

  inspectNode(node) {
    this.selectedNode = node;
  }

  setStudioWriteState(state, engineMode = "HYDRADB BOLT") {
    const indicator = document.getElementById("studioWriteIndicator");
    const engine = document.getElementById("studioEngineMode");
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
