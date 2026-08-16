class App {
  constructor() {
    this.currentSessionId = this.sessionFromUrl() || "default";
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
    if (this.currentView === "studio") this.refreshStudio();
  }

  sessionFromUrl() {
    return new URLSearchParams(window.location.search).get("session");
  }

  bindControls() {
    document.getElementById("btnLaunchStudio")?.addEventListener("click", () => {
      if (this.currentView === "studio") this.showView("landing");
      else this.openDemoStudio();
    });
    document.getElementById("heroLaunchButton")?.addEventListener("click", () => this.openDemoStudio());
    document.getElementById("btnViewLiveGraph")?.addEventListener("click", () => this.openDemoStudio());
    document.getElementById("navDebuggerStudio")?.addEventListener("click", () => this.showView("studio"));
    document.getElementById("btnLoadDemo")?.addEventListener("click", () => this.openDemoStudio());
    ["btnBackOverview", "brandButton"].forEach((id) => {
      document.getElementById(id)?.addEventListener("click", () => this.showView("landing"));
    });
    window.addEventListener("hashchange", () => {
      const view = window.location.hash.startsWith("#studio") ? "studio" : "landing";
      if (view !== this.currentView) this.showView(view, false);
    });

    const sessionInput = document.getElementById("sessionInput");
    if (sessionInput) sessionInput.value = this.currentSessionId;
    document.getElementById("sessionForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      this.currentSessionId = sessionInput.value.trim() || "default";
      const url = new URL(window.location.href);
      url.searchParams.set("session", this.currentSessionId);
      url.hash = "studio";
      window.history.replaceState({}, "", url);
      await this.refreshStudio();
    });

    document.getElementById("btnTriggerInvalidate")?.addEventListener("click", () => {
      if (!this.selectedNode || this.selectedNode.kind !== "FACT") {
        this.message("Select a fact node in the graph before invalidating.", true);
        return;
      }
      document.getElementById("modalFactId").value = this.selectedNode.id;
      document.getElementById("modalReason").value = "";
      document.getElementById("modalReplacement").value = "";
      document.getElementById("modalEvidence").value = "";
      document.getElementById("invalidateModal").showModal();
    });
    document.getElementById("btnModalCancel")?.addEventListener("click", () => document.getElementById("invalidateModal").close());
    document.getElementById("invalidateForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = event.submitter;
      this.setBusy(button, true, "Invalidating...");
      try {
        const result = await API.invalidateFact(this.currentSessionId, {
          fact_id: document.getElementById("modalFactId").value,
          reason: document.getElementById("modalReason").value,
          replacement_value: document.getElementById("modalReplacement").value || null,
          evidence_uri: document.getElementById("modalEvidence").value || null,
          auto_heal: false
        });
        document.getElementById("invalidateModal").close();
        this.graphVisualizer.setBlastRadiusHighlight(result.blast_radius.affected_nodes.map((node) => node.id));
        this.message(`${result.blast_radius.affected_nodes_count} downstream nodes marked stale.`);
        await this.refreshStudio();
      } catch (error) {
        this.message(`Invalidation failed: ${error.message}`, true);
      } finally {
        this.setBusy(button, false, "Invalidate fact");
      }
    });
    document.getElementById("btnAutoHeal")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      this.setBusy(button, true, "Executing...");
      try {
        const result = await API.healSubgraph(this.currentSessionId);
        this.message(result.message, !result.success);
        await this.refreshStudio();
      } catch (error) {
        this.message(`Execution failed: ${error.message}`, true);
      } finally {
        this.setBusy(button, false, "Execute stale subgraph");
      }
    });
    document.getElementById("btnThemeToggle")?.addEventListener("click", () => {
      const theme = document.documentElement.classList.contains("theme-light") ? "dark" : "light";
      this.applyTheme(theme);
      localStorage.setItem("echotrace_theme", theme);
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

  async openDemoStudio() {
    const button = document.getElementById("btnLoadDemo");
    this.setBusy(button, true, "Loading demo...");
    try {
      const demo = await API.loadMemoryStory();
      this.currentSessionId = demo.session_id;
      const input = document.getElementById("sessionInput");
      if (input) input.value = this.currentSessionId;
      const url = new URL(window.location.href);
      url.searchParams.set("session", this.currentSessionId);
      url.hash = "studio";
      window.history.replaceState({}, "", url);
      this.showView("studio", false);
      this.message(`Answer: ${demo.answer.answer}. Source: ${demo.answer.evidence[0].session_id}. Earlier memory: ${demo.answer.history[0].value}.`);
      await this.refreshStudio();
    } catch (error) {
      this.currentSessionId = "memory:demo-user";
      const input = document.getElementById("sessionInput");
      if (input) input.value = this.currentSessionId;
      this.showView("studio", false);
      try {
        await this.refreshStudio();
        this.message("Loaded the existing demo graph after a temporary seed connection error.");
      } catch (loadError) {
        this.message(`Demo load failed: ${loadError.message}`, true);
      }
    } finally {
      this.setBusy(button, false, "Load demo story");
    }
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
      const graph = await API.getGraph(this.currentSessionId);
      this.graphVisualizer.setData(graph.nodes || [], graph.edges || []);
      const empty = document.getElementById("emptyGraphState");
      if (empty) {
        empty.classList.toggle("hidden", graph.nodes.length > 0);
        empty.classList.toggle("grid", graph.nodes.length === 0);
      }
      await this.healthMonitor.fetchAndRender(this.currentSessionId);
      const times = graph.nodes.map((node) => Date.parse(node.valid_from)).filter(Number.isFinite);
      if (times.length) this.timelineController.setRange(new Date(Math.min(...times)).toISOString(), new Date().toISOString());
      this.graphVisualizer.resizeCanvas();
    } catch (error) {
      this.message(`Session load failed: ${error.message}`, true);
    }
  }

  inspectNode(node) {
    this.selectedNode = node;
    document.getElementById("inspNodeId").textContent = node.id;
    document.getElementById("inspKind").textContent = node.kind;
    document.getElementById("inspLabel").textContent = node.label;
    const status = document.getElementById("inspStatus");
    status.textContent = node.is_stale ? "STALE" : (node.status || "ACTIVE");
    status.className = node.is_stale ? "text-status-warning font-bold" : "text-status-healthy font-bold";
    const evidence = document.getElementById("inspEvidenceWrap");
    evidence.classList.toggle("hidden", !node.source_uri);
    document.getElementById("inspEvidence").textContent = node.source_uri || "";
    const content = document.getElementById("inspCodeBlockWrap");
    content.classList.toggle("hidden", !node.content);
    document.getElementById("inspCodeBlock").textContent = node.content || "";
  }

  setBusy(button, busy, label) {
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle("opacity-60", busy);
    const text = Array.from(button.childNodes).find((node) => node.nodeType === Node.TEXT_NODE);
    if (text) text.textContent = label;
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
