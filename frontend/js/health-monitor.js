/**
 * Memory Health and Contradiction Panel Controller
 * Formatted for EchoTrace Stitch Dark Theme
 */
class HealthMonitor {
  constructor() {
    this.scoreVal = document.getElementById('healthScoreDisplay');
    this.indicator = document.getElementById('healthIndicator');
    this.statActiveFacts = document.getElementById('statActiveFacts');
    this.statStaleDecisions = document.getElementById('statStaleDecisions');
    this.statContradictions = document.getElementById('statContradictions');
    this.statSuperseded = document.getElementById('statSuperseded');
    this.contradictionContainer = document.getElementById('contradictionContainer');
  }

  async fetchAndRender(sessionId) {
    try {
      const report = await window.apiClient.getMemoryHealth(sessionId);
      this.update(report);
    } catch (err) {
      console.error('Failed to fetch memory health:', err);
    }
  }

  update(report) {
    if (!report) return;
    const score = report.health_score !== undefined ? report.health_score : 100;

    if (this.scoreVal) {
      this.scoreVal.textContent = `${score}%`;
      if (score >= 90) {
        this.scoreVal.style.color = '#2ECC71';
      } else if (score >= 60) {
        this.scoreVal.style.color = '#F59E0B';
      } else {
        this.scoreVal.style.color = '#E11D48';
      }
    }

    if (this.indicator) {
      if (score >= 90) {
        this.indicator.style.background = '#2ECC71';
        this.indicator.style.boxShadow = '0 0 8px rgba(46, 204, 113, 0.4)';
      } else if (score >= 60) {
        this.indicator.style.background = '#F59E0B';
        this.indicator.style.boxShadow = '0 0 8px rgba(245, 158, 11, 0.4)';
      } else {
        this.indicator.style.background = '#E11D48';
        this.indicator.style.boxShadow = '0 0 8px rgba(225, 29, 72, 0.4)';
      }
    }

    if (this.statActiveFacts) this.statActiveFacts.textContent = report.valid_facts || 0;
    if (this.statStaleDecisions) {
      const stale = (report.stale_decisions || 0) + (report.stale_artifacts || 0);
      this.statStaleDecisions.textContent = stale;
    }
    if (this.statSuperseded) this.statSuperseded.textContent = report.superseded_facts || 0;

    const conflicts = report.active_contradictions || [];
    if (this.statContradictions) this.statContradictions.textContent = conflicts.length;

    if (this.contradictionContainer) {
      this.contradictionContainer.innerHTML = '';
      if (conflicts.length > 0) {
        conflicts.forEach(c => {
          const card = document.createElement('div');
          card.className = 'border border-status-warning/40 bg-status-warning/10 rounded p-2.5 font-mono text-[11px]';
          card.innerHTML = `
            <div class="text-status-warning font-bold uppercase flex items-center gap-1">
              <span class="material-symbols-outlined text-[13px]">warning</span>
              CONFLICT: ${c.entity} &bull; ${c.property_name}
            </div>
            <div class="text-text-secondary mt-1">
              Agent A: <span class="text-text-primary font-semibold">"${c.fact_a_value}"</span> vs Agent B: <span class="text-text-primary font-semibold">"${c.fact_b_value}"</span>
            </div>
          `;
          this.contradictionContainer.appendChild(card);
        });
      }
    }
  }
}
