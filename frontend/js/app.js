/* EchoTrace Application Coordinator & Interactive Demo Controller */

class App {
  constructor() {
    this.currentSessionId = "api_deprecation_demo";
    this.selectedNode = null;
    this.blastRadiusNodes = new Set();
    this.currentView = "landing"; // "landing" | "studio"
    this.init();
  }

  async init() {
    this.bindThemeToggle();
    this.checkEngineHealth();
    this.bindViewSwitching();
    this.bindSimulatorControls();
    this.bindStudioControls();
    this.bindModalControls();

    // Initialize visualizer with canvas
    window.graphVisualizer = new GraphVisualizer("studioGraphCanvas");
    window.healthMonitor = new HealthMonitor();
    window.timelineController = new TimelineController();

    // Handle initial route
    if (window.location.hash === "#studio") {
      this.switchView("studio");
    } else {
      this.switchView("landing");
    }

    // Preload scenario
    await this.loadScenario("api-deprecation");
  }

  bindThemeToggle() {
    const btn = document.getElementById("btnThemeToggle");
    const savedTheme = localStorage.getItem("echotrace_theme") || "dark";
    this.applyTheme(savedTheme);

    if (btn) {
      btn.addEventListener("click", () => {
        const isLight = document.documentElement.classList.contains("theme-light");
        const nextTheme = isLight ? "dark" : "light";
        this.applyTheme(nextTheme);
        localStorage.setItem("echotrace_theme", nextTheme);
      });
    }
  }

  applyTheme(theme) {
    const icon = document.getElementById("themeIcon");
    if (theme === "light") {
      document.documentElement.classList.remove("dark");
      document.documentElement.classList.add("theme-light");
      if (icon) icon.textContent = "dark_mode";
    } else {
      document.documentElement.classList.remove("theme-light");
      document.documentElement.classList.add("dark");
      if (icon) icon.textContent = "light_mode";
    }
    if (window.graphVisualizer) {
      window.graphVisualizer.draw();
    }
  }

  bindViewSwitching() {
    const btnToggle = document.getElementById("btnToggleStudio");
    const btnHeroLaunch = document.getElementById("heroLaunchBtn");
    const btnBack = document.getElementById("btnBackToLanding");
    const navBrand = document.getElementById("navBrandBtn");

    if (btnToggle) {
      btnToggle.addEventListener("click", () => {
        if (this.currentView === "landing") {
          this.switchView("studio");
        } else {
          this.switchView("landing");
        }
      });
    }

    if (btnHeroLaunch) {
      btnHeroLaunch.addEventListener("click", () => {
        this.switchView("studio");
      });
    }

    if (btnBack) {
      btnBack.addEventListener("click", () => {
        this.switchView("landing");
      });
    }

    if (navBrand) {
      navBrand.addEventListener("click", () => {
        this.switchView("landing");
      });
    }

    window.addEventListener("hashchange", () => {
      if (window.location.hash === "#studio") {
        this.switchView("studio");
      } else if (window.location.hash === "#landing" || window.location.hash === "") {
        this.switchView("landing");
      }
    });
  }

  switchView(viewName) {
    this.currentView = viewName;
    const viewLanding = document.getElementById("viewLanding");
    const viewStudio = document.getElementById("viewStudio");
    const toggleLabel = document.getElementById("toggleStudioLabel");
    const toggleIcon = document.getElementById("toggleStudioIcon");
    const navLinks = document.getElementById("navLandingLinks");

    if (viewName === "studio") {
      if (viewLanding) viewLanding.classList.add("hidden");
      if (viewStudio) {
        viewStudio.classList.remove("hidden");
        viewStudio.classList.add("flex");
      }
      if (toggleLabel) toggleLabel.textContent = "Back to Story";
      if (toggleIcon) toggleIcon.textContent = "menu_book";
      if (navLinks) navLinks.classList.add("opacity-40", "pointer-events-none");
      window.location.hash = "studio";

      // Refresh layout on canvas
      setTimeout(() => {
        if (window.graphVisualizer) {
          window.graphVisualizer.resizeCanvas();
        }
      }, 100);
    } else {
      if (viewStudio) {
        viewStudio.classList.add("hidden");
        viewStudio.classList.remove("flex");
      }
      if (viewLanding) viewLanding.classList.remove("hidden");
      if (toggleLabel) toggleLabel.textContent = "Launch App";
      if (toggleIcon) toggleIcon.textContent = "rocket_launch";
      if (navLinks) navLinks.classList.remove("opacity-40", "pointer-events-none");
      if (window.location.hash === "#studio") {
        window.location.hash = "landing";
      }
    }
  }

  async checkEngineHealth() {
    try {
      const health = await window.apiClient.getHealth();
      const dot = document.getElementById("headerEngineDot");
      const label = document.getElementById("headerEngineLabel");
      if (dot && label) {
        if (health.hydradb_connected) {
          dot.className = "w-1.5 h-1.5 rounded-full bg-status-healthy animate-pulse-glow";
          label.textContent = "HYDRADB BOLT";
          label.className = "text-[10px] text-status-healthy font-semibold";
        } else {
          dot.className = "w-1.5 h-1.5 rounded-full bg-vermilion animate-pulse-glow";
          label.textContent = "INTERNAL ENGINE";
          label.className = "text-[10px] text-vermilion font-semibold";
        }
      }
    } catch (err) {
      console.warn("Engine health check warning:", err);
    }
  }

  /* 1. The Interactive Dual-Pane Trace Simulator on Landing */
  bindSimulatorControls() {
    const btnSimBreak = document.getElementById("btnSimBreak");
    const btnSimHeal = document.getElementById("btnSimHeal");
    const simStatusChip = document.getElementById("simStatusChip");
    const nResearch = document.getElementById("node-research");
    const nPlanner = document.getElementById("node-planner");
    const nCoding = document.getElementById("node-coding");
    const nTesting = document.getElementById("node-testing");

    const sResearch = document.getElementById("status-research");
    const sPlanner = document.getElementById("status-planner");
    const sCoding = document.getElementById("status-coding");
    const sTesting = document.getElementById("status-testing");

    const simFactTag = document.getElementById("simFactTag");
    const simFactTitle = document.getElementById("simFactTitle");
    const simPlanTag = document.getElementById("simPlanTag");
    const simCodeTag = document.getElementById("simCodeTag");
    const simTestTag = document.getElementById("simTestTag");

    const simResultHeading = document.getElementById("simResultHeading");
    const simCodePreview = document.getElementById("simCodePreview");
    const simDiagnosisText = document.getElementById("simDiagnosisText");

    if (btnSimBreak && btnSimHeal) {
      btnSimBreak.addEventListener("click", () => {
        // Step 1: Invalidate root fact node
        if (sResearch) {
          sResearch.className = "absolute -left-[40px] top-4 w-6 h-6 rounded-full bg-status-warning flex items-center justify-center z-10 border border-bg-canvas";
          sResearch.innerHTML = '<span class="material-symbols-outlined text-xs text-white font-bold">warning</span>';
        }
        if (nResearch) nResearch.style.borderColor = "#E11D48";
        if (simFactTag) { simFactTag.textContent = "INVALIDATED"; simFactTag.style.color = "#E11D48"; }
        if (simFactTitle) simFactTitle.textContent = "PaymentsAPI: Version = v1 (DEPRECATED)";

        // Step 2: Cascade failure to dependent downstream nodes
        [
          { n: nPlanner, s: sPlanner, tag: simPlanTag, msg: "STALE DECISION" },
          { n: nCoding, s: sCoding, tag: simCodeTag, msg: "CORRUPTED CODE" },
          { n: nTesting, s: sTesting, tag: simTestTag, msg: "BROKEN TESTS" }
        ].forEach(item => {
          if (item.s) {
            item.s.className = "absolute -left-[40px] top-4 w-6 h-6 rounded-full bg-surface-container-high flex items-center justify-center z-10 border border-bg-canvas";
            item.s.innerHTML = '<span class="material-symbols-outlined text-xs text-text-secondary font-bold">close</span>';
          }
          if (item.n) {
            item.n.style.borderColor = "#E11D48";
            item.n.style.opacity = "0.7";
          }
          if (item.tag) {
            item.tag.textContent = item.msg;
            item.tag.style.color = "#E11D48";
          }
        });

        if (simStatusChip) {
          simStatusChip.textContent = "CASCADE CONTAMINATION DETECTED (3 NODES)";
          simStatusChip.className = "px-2 py-0.5 rounded bg-status-warning/10 text-status-warning font-semibold";
        }

        if (simResultHeading) simResultHeading.textContent = "payments_client.py (CRITICAL: TARGETING DEPRECATED v1 API)";
        if (simCodePreview) {
          simCodePreview.textContent = `import requests
from sdk.echotrace import EchoTrace

tracer = EchoTrace(session_id="production_checkout")

@tracer.agent(name="IntegrationCoder", role="Software Engineer")
class PaymentsClient:
    def __init__(self, api_key: str):
        # [CRITICAL ERROR] API v1 was deprecated on Aug 12; endpoint returns 404
        self.base_url = "https://api.payments-corp.com/v1" # DEPRECATED
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def charge(self, amount: int, currency: str = "USD"):
        url = f"{self.base_url}/charges"
        payload = {"amount": amount, "currency": currency}
        return requests.post(url, json=payload, headers=self.headers)`;
        }

        if (simDiagnosisText) {
          simDiagnosisText.innerHTML = '<span class="text-status-warning font-bold">HYDRADB BLAST RADIUS TRAVERSAL:</span> Root fact invalidated. 1 Decision, 1 Code Artifact, and 1 Test Suite marked stale. Click Auto-Heal to repair.';
        }

        btnSimBreak.disabled = true;
        btnSimBreak.classList.add("opacity-50", "cursor-not-allowed");
        btnSimHeal.disabled = false;
        btnSimHeal.classList.remove("opacity-50", "cursor-not-allowed");

        if (window.graphVisualizer) {
          window.graphVisualizer.setBlastRadiusHighlight(["dec_use_v1", "dec_generate_client", "art_client_py", "dec_generate_test", "art_test_py"]);
        }

        const btnStudioHeal = document.getElementById("btnAutoHeal");
        if (btnStudioHeal) {
          btnStudioHeal.disabled = false;
          btnStudioHeal.classList.remove("opacity-50", "cursor-not-allowed");
        }
      });

      btnSimHeal.addEventListener("click", () => {
        // Step 1: Reset root fact node to healed state
        if (sResearch) {
          sResearch.className = "absolute -left-[40px] top-4 w-6 h-6 rounded-full bg-status-healthy flex items-center justify-center z-10 border border-bg-canvas";
          sResearch.innerHTML = '<span class="material-symbols-outlined text-xs text-bg-canvas font-bold">check</span>';
        }
        if (nResearch) nResearch.style.borderColor = "#2A2E35";
        if (simFactTag) { simFactTag.textContent = "v2 (ACTIVE)"; simFactTag.style.color = "#2ECC71"; }
        if (simFactTitle) simFactTitle.textContent = "PaymentsAPI: Version = v2 (SUPERSEDED)";

        // Step 2: Stagger re-execution of downstream nodes in topological order
        [
          { n: nPlanner, s: sPlanner, tag: simPlanTag, msg: "+142ms (RE-EVALUATED)" },
          { n: nCoding, s: sCoding, tag: simCodeTag, msg: "+850ms (REGENERATED)" },
          { n: nTesting, s: sTesting, tag: simTestTag, msg: "+1200ms (PASSING)" }
        ].forEach((item, idx) => {
          setTimeout(() => {
            if (item.s) {
              item.s.className = "absolute -left-[40px] top-4 w-6 h-6 rounded-full bg-status-healthy flex items-center justify-center z-10 border border-bg-canvas transition-all duration-300";
              item.s.innerHTML = '<span class="material-symbols-outlined text-xs text-bg-canvas font-bold">check</span>';
            }
            if (item.n) {
              item.n.style.borderColor = "#2A2E35";
              item.n.style.opacity = "1";
            }
            if (item.tag) {
              item.tag.textContent = item.msg;
              item.tag.style.color = "#2ECC71";
            }
          }, (idx + 1) * 250);
        });

        if (simStatusChip) {
          simStatusChip.textContent = "STATUS: 100% HEALTHY (AUTO-HEALED)";
          simStatusChip.className = "px-2 py-0.5 rounded bg-status-healthy/10 text-status-healthy font-semibold";
        }

        if (simResultHeading) simResultHeading.textContent = "payments_client.py (AUTO-HEALED FOR API v2)";
        if (simCodePreview) {
          simCodePreview.textContent = `import requests
from sdk.echotrace import EchoTrace

tracer = EchoTrace(session_id="production_checkout")

@tracer.agent(name="IntegrationCoder", role="Software Engineer")
class PaymentsClient:
    def __init__(self, api_key: str):
        # [AUTO-HEALED] Regenerated in topological dependency order targeting v2 spec
        self.base_url = "https://api.payments-corp.com/v2" # MIGRATED
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def charge(self, amount: int, currency: str = "USD"):
        url = f"{self.base_url}/charges"
        payload = {"amount": amount, "currency": currency}
        return requests.post(url, json=payload, headers=self.headers)`;
        }

        if (simDiagnosisText) {
          simDiagnosisText.innerHTML = '<span class="text-status-healthy font-bold">AUTO-HEAL COMPLETE:</span> Downstream agents re-executed in topological dependency order. All artifacts and test suites refreshed cleanly.';
        }

        btnSimBreak.disabled = false;
        btnSimBreak.classList.remove("opacity-50", "cursor-not-allowed");
        btnSimHeal.disabled = true;
        btnSimHeal.classList.add("opacity-50", "cursor-not-allowed");

        if (window.graphVisualizer) {
          window.graphVisualizer.setBlastRadiusHighlight([]);
        }

        const btnStudioHeal = document.getElementById("btnAutoHeal");
        if (btnStudioHeal) {
          btnStudioHeal.disabled = true;
          btnStudioHeal.classList.add("opacity-50", "cursor-not-allowed");
        }
      });
    }
  }

  /* 2. Studio Controls & Actions */
  bindStudioControls() {
    const btnDeprecate = document.getElementById("btnScenarioDeprecate");
    const btnContradict = document.getElementById("btnScenarioContradict");
    const btnReset = document.getElementById("btnResetGraph");
    const btnRunFullSim = document.getElementById("btnRunFullSim");
    const btnTriggerInvalidate = document.getElementById("btnTriggerInvalidate");
    const btnAutoHeal = document.getElementById("btnAutoHeal");

    if (btnDeprecate) {
      btnDeprecate.addEventListener("click", () => this.loadScenario("api-deprecation"));
    }
    if (btnContradict) {
      btnContradict.addEventListener("click", () => this.loadScenario("contradiction"));
    }
    if (btnReset) {
      btnReset.addEventListener("click", () => this.loadScenario("api-deprecation"));
    }
    if (btnRunFullSim) {
      btnRunFullSim.addEventListener("click", async () => {
        try {
          btnRunFullSim.textContent = "Running Sim...";
          const res = await window.apiClient.runSimulation("live_simulation");
          this.currentSessionId = "live_simulation";
          document.getElementById("currentSessionLabel").textContent = this.currentSessionId;
          await this.refreshStudio();
          btnRunFullSim.textContent = "Run Full Sim";
          alert(`Simulation complete! Affected: ${res.affected_downstream_count} nodes. Auto-healed: ${res.re_executed_nodes.length} nodes.`);
        } catch (err) {
          btnRunFullSim.textContent = "Run Full Sim";
          alert("Simulation failed: " + err.message);
        }
      });
    }

    if (btnTriggerInvalidate) {
      btnTriggerInvalidate.addEventListener("click", () => {
        if (!this.selectedNode) {
          alert("Please click on a Fact node on the canvas to invalidate.");
          return;
        }
        if (this.selectedNode.kind !== "FACT") {
          alert("Selected node is a " + this.selectedNode.kind + ". You can only invalidate FACT nodes.");
          return;
        }
        this.openInvalidateModal(this.selectedNode);
      });
    }

    if (btnAutoHeal) {
      btnAutoHeal.addEventListener("click", async () => {
        await this.autoHealSession();
      });
    }
  }

  /* 3. Invalidation Modal Dialog Bindings */
  bindModalControls() {
    const modal = document.getElementById("invalidateModal");
    const btnCancel = document.getElementById("btnModalCancel");
    const btnConfirm = document.getElementById("btnModalConfirm");

    if (btnCancel && modal) {
      btnCancel.addEventListener("click", () => {
        modal.classList.add("hidden");
        modal.classList.remove("flex");
      });
    }

    if (btnConfirm && modal) {
      btnConfirm.addEventListener("click", async () => {
        const factId = document.getElementById("modalFactId").value;
        const reason = document.getElementById("modalReason").value || "Superseded by updated documentation";
        const replacement = document.getElementById("modalReplacement").value || "v2";
        const evidence = document.getElementById("modalEvidence").value || "https://docs.payments.com/v2";

        try {
          const res = await window.apiClient.invalidateFact(this.currentSessionId, {
            fact_id: factId,
            reason: reason,
            replacement_value: replacement,
            evidence_uri: evidence,
            auto_heal: false
          });

          modal.classList.add("hidden");
          modal.classList.remove("flex");

          // Refresh graph and highlight blast radius
          await this.refreshStudio();
          if (res.blast_radius && res.blast_radius.affected_nodes) {
            const nodeIds = res.blast_radius.affected_nodes.map(n => n.id || n.node_id);
            window.graphVisualizer.setBlastRadiusHighlight(nodeIds);
            const btnHeal = document.getElementById("btnAutoHeal");
            if (btnHeal) {
              btnHeal.disabled = false;
              btnHeal.classList.remove("opacity-50", "cursor-not-allowed");
            }
          }
        } catch (err) {
          alert("Invalidation failed: " + err.message);
        }
      });
    }
  }

  openInvalidateModal(node) {
    const modal = document.getElementById("invalidateModal");
    if (!modal) return;
    document.getElementById("modalFactId").value = node.id;
    document.getElementById("modalReplacement").value = node.property_value ? node.property_value + "_v2" : "v2";
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  }

  async loadScenario(name) {
    try {
      if (name === "api-deprecation") {
        await window.apiClient.loadScenario("api-deprecation", "api_deprecation_demo");
        this.currentSessionId = "api_deprecation_demo";
      } else {
        await window.apiClient.loadScenario("contradiction", "contradiction_demo");
        this.currentSessionId = "contradiction_demo";
      }
      document.getElementById("currentSessionLabel").textContent = this.currentSessionId;
      await this.refreshStudio();
    } catch (err) {
      console.error("Failed to load scenario:", err);
    }
  }

  async refreshStudio() {
    try {
      const graphData = await window.apiClient.getGraph(this.currentSessionId);
      if (window.graphVisualizer) {
        window.graphVisualizer.setData(graphData.nodes || [], graphData.edges || []);
      }
      if (window.healthMonitor) {
        await window.healthMonitor.fetchAndRender(this.currentSessionId);
      }
    } catch (err) {
      console.error("Failed to refresh studio:", err);
    }
  }

  async autoHealSession() {
    try {
      const res = await window.apiClient.healSubgraph(this.currentSessionId);
      alert(`Auto-Heal Complete: Re-executed ${res.re_executed_nodes.length} contaminated nodes in topological order.`);
      const btnHeal = document.getElementById("btnAutoHeal");
      if (btnHeal) {
        btnHeal.disabled = true;
        btnHeal.classList.add("opacity-50", "cursor-not-allowed");
      }
      if (window.graphVisualizer) {
        window.graphVisualizer.setBlastRadiusHighlight([]);
      }
      await this.refreshStudio();
    } catch (err) {
      alert("Auto-heal failed: " + err.message);
    }
  }

  inspectNode(node) {
    this.selectedNode = node;
    document.getElementById("inspNodeId").textContent = node.id || "-";
    document.getElementById("inspKind").textContent = node.kind || "-";
    document.getElementById("inspLabel").textContent = node.label || "-";
    document.getElementById("inspStatus").textContent = node.status || (node.is_stale ? "STALE" : "HEALTHY");

    const codeWrap = document.getElementById("inspCodeBlockWrap");
    const codeBlock = document.getElementById("inspCodeBlock");
    if (node.content) {
      codeWrap.style.display = "flex";
      codeBlock.textContent = node.content;
    } else {
      codeWrap.style.display = "none";
    }

    const evWrap = document.getElementById("inspEvidenceWrap");
    const evVal = document.getElementById("inspEvidence");
    if (node.evidence_source || node.uri || node.source_uri) {
      evWrap.style.display = "flex";
      evVal.textContent = node.evidence_source || node.uri || node.source_uri;
    } else {
      evWrap.style.display = "none";
    }
  }
}

// Global application bootstrap
window.addEventListener("DOMContentLoaded", () => {
  window.app = new App();
});
