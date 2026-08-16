/**
 * Time-Travel Historical Memory State Scrubber
 * Formatted for Obscura Warm Obsidian & Electric Vermilion Theme
 */
class TimelineController {
  constructor() {
    this.slider = document.getElementById('timeTravelSlider');
    this.label = document.getElementById('sliderTimeDisplay');
    this.btnReset = document.getElementById('btnTimeTravelReset');

    this.minTimestamp = null;
    this.maxTimestamp = null;

    this.setupEvents();
  }

  setRange(minIso, maxIso) {
    if (!this.slider || !this.label) return;
    this.minTimestamp = new Date(minIso).getTime();
    this.maxTimestamp = new Date(maxIso).getTime();

    this.slider.min = '0';
    this.slider.max = '100';
    this.slider.value = '100';
    this.label.textContent = 'SNAPSHOT: CURRENT (LIVE)';
  }

  setupEvents() {
    if (!this.slider || !this.label) return;

    this.slider.addEventListener('input', async (e) => {
      const val = parseInt(e.target.value, 10);
      if (val === 100) {
        this.label.textContent = 'SNAPSHOT: CURRENT (LIVE)';
        if (window.app) {
          await window.app.refreshStudio();
        }
        return;
      }

      if (!this.minTimestamp || !this.maxTimestamp) return;

      const currentMs = this.minTimestamp + (this.maxTimestamp - this.minTimestamp) * (val / 100.0);
      const currentDate = new Date(currentMs);
      const isoString = currentDate.toISOString();

      this.label.textContent = `SNAPSHOT: ${currentDate.toLocaleTimeString()} (${currentDate.toLocaleDateString()})`;

      if (window.apiClient && window.app && window.app.graphVisualizer) {
        try {
          const snapshotData = await window.apiClient.getGraph(window.app.currentSessionId, isoString);
          window.app.graphVisualizer.setData(snapshotData.nodes || [], snapshotData.edges || []);
        } catch (err) {
          console.error('Time travel failed:', err);
        }
      }
    });

    if (this.btnReset) {
      this.btnReset.addEventListener('click', async () => {
        this.slider.value = '100';
        this.label.textContent = 'SNAPSHOT: CURRENT (LIVE)';
        if (window.app) {
          await window.app.refreshStudio();
        }
      });
    }
  }

  resetToLive() {
    if (this.slider && this.label) {
      this.slider.value = '100';
      this.label.textContent = 'SNAPSHOT: CURRENT (LIVE)';
    }
  }
}
