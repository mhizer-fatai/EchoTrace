/**
 * Interactive DAG Graph Visualizer using HTML5 Canvas
 * Designed for EchoTrace Stitch Dark Theme & HydraDB Provenance Aesthetic
 */
class GraphVisualizer {
  constructor(canvasId, onNodeSelected) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.onNodeSelected = onNodeSelected || ((node) => {
      if (window.app && window.app.inspectNode) {
        window.app.inspectNode(node);
      }
    });

    this.nodes = [];
    this.edges = [];
    this.nodeMap = new Map();
    this.blastRadiusSet = new Set();

    this.panX = 0;
    this.panY = 0;
    this.zoom = 1;

    this.isDragging = false;
    this.dragStartX = 0;
    this.dragStartY = 0;

    this.hoveredNode = null;
    this.selectedNode = null;
    this.animFrameId = null;

    this.resizeCanvas();
    window.addEventListener('resize', () => this.resizeCanvas());
    this.setupEvents();
    this.startAnimationLoop();
  }

  resizeCanvas() {
    if (!this.canvas || !this.canvas.parentElement) return;
    const parent = this.canvas.parentElement;
    this.canvas.width = parent.clientWidth || 900;
    this.canvas.height = parent.clientHeight || 560;
    if (this.nodes.length > 0) {
      this.calculateHierarchicalLayout();
    }
  }

  setData(nodesOrData, edgesMaybe) {
    let rawNodes = [];
    let rawEdges = [];

    if (Array.isArray(nodesOrData)) {
      rawNodes = nodesOrData;
      rawEdges = edgesMaybe || [];
    } else if (nodesOrData && typeof nodesOrData === 'object') {
      rawNodes = nodesOrData.nodes || [];
      rawEdges = nodesOrData.edges || [];
    }

    this.nodes = rawNodes.map(n => ({
      ...n,
      x: n.x || 0,
      y: n.y || 0,
      radius: n.kind === 'AGENT' ? 22 : n.kind === 'DECISION' ? 18 : n.kind === 'MESSAGE' ? 17 : 16
    }));
    this.edges = rawEdges;
    this.nodeMap.clear();
    this.nodes.forEach(n => this.nodeMap.set(n.id, n));

    this.newNodeHighlight = this.newestNodeId();
    this.calculateHierarchicalLayout();
  }

  newestNodeId() {
    let newest = null;
    let newestTime = -Infinity;
    this.nodes.forEach((n) => {
      const t = Date.parse(n.valid_from || n.created_at || "");
      if (Number.isFinite(t) && t > newestTime) {
        newestTime = t;
        newest = n.id;
      }
    });
    return newest;
  }

  setBlastRadiusHighlight(nodeIdArray) {
    this.blastRadiusSet = new Set(nodeIdArray || []);
    this.nodes.forEach(n => {
      if (this.blastRadiusSet.has(n.id)) {
        n.is_stale = true;
      }
    });
  }

  getCleanShortLabel(node) {
    if (node.kind === 'AGENT') {
      return node.label ? node.label.replace(' Agent', '') : node.id.replace('agent_', '');
    }
    if (node.kind === 'EVIDENCE') {
      if (node.label && node.label.includes(':')) {
        return node.label.split(':')[1].trim();
      }
      return node.id;
    }
    if (node.kind === 'MESSAGE') {
      return node.source_session_id ? `${node.source_session_id}: message` : (node.label || node.id);
    }
    if (node.kind === 'FACT') {
      if (node.entity && node.property_value) {
        return `${node.entity}: ${node.property_value}`;
      }
      if (node.label) return node.label;
      return node.id;
    }
    if (node.kind === 'DECISION') {
      if (node.action_type) return node.action_type;
      if (node.label) return node.label.replace('Decision: ', '');
      return node.id;
    }
    if (node.kind === 'ARTIFACT') {
      return node.artifact_name || (node.label ? node.label.replace('Artifact: ', '') : node.id);
    }
    return node.label || node.id;
  }

  calculateHierarchicalLayout() {
    const width = this.canvas.width || 900;
    const height = this.canvas.height || 560;

    const tiers = {
      AGENT: [],
      EVIDENCE: [],
      MESSAGE: [],
      FACT: [],
      DECISION: [],
      ARTIFACT: []
    };

    this.nodes.forEach(node => {
      const kind = node.kind || 'FACT';
      if (tiers[kind]) {
        tiers[kind].push(node);
      } else {
        tiers.FACT.push(node);
      }
    });

    const tierKeys = ['MESSAGE', 'EVIDENCE', 'FACT', 'AGENT', 'DECISION', 'ARTIFACT'];
    const activeTiers = tierKeys.filter(k => tiers[k].length > 0);
    const tierGap = 120;
    const nodeGap = 34;
    const margin = 90;
    const labelSpace = 34;
    const maxTierWidth = Math.max(320, width - margin * 2);
    const maxPerRow = Math.max(1, Math.floor((maxTierWidth + nodeGap) / (nodeGap + 56)));
    const usableHeight = height - margin * 2;

    const tierPositions = {};
    let cursorY = margin;
    activeTiers.forEach((tierName, tierIdx) => {
      const tierNodes = tiers[tierName];
      const count = tierNodes.length;
      const rows = Math.max(1, Math.ceil(count / maxPerRow));
      const tierHeight = rows * (56 + labelSpace);
      const startY = cursorY;
      const centerX = width / 2;

      tierNodes.forEach((node, nodeIdx) => {
        const row = Math.floor(nodeIdx / maxPerRow);
        const col = nodeIdx % maxPerRow;
        const rowCount = Math.min(maxPerRow, count - row * maxPerRow);
        const rowWidth = (rowCount - 1) * nodeGap + 56;
        const startX = centerX - rowWidth / 2;
        node.x = startX + col * nodeGap + 28;
        node.y = startY + row * (56 + labelSpace) + 28;
      });
      tierPositions[tierName] = { startY, endY: startY + tierHeight };
      cursorY += tierHeight + tierGap;
      void tierIdx;
    });

    // If the total content is taller than the canvas, scale down compactly
    const totalUsed = cursorY - tierGap + margin;
    const fitScale = Math.min(1, usableHeight / Math.max(1, totalUsed - margin));
    if (fitScale < 1) {
      this.nodes.forEach(node => {
        node.x = width / 2 + (node.x - width / 2) * fitScale;
        node.y = margin + (node.y - margin) * fitScale;
      });
    }

    this.panX = 0;
    this.panY = 0;
    this.zoom = fitScale < 1 ? fitScale : 1;
  }

  setupEvents() {
    this.canvas.addEventListener('mousedown', e => {
      const pos = this.getCanvasCoords(e);
      const clicked = this.findNodeAt(pos.x, pos.y);

      if (clicked) {
        this.selectedNode = clicked;
        if (this.onNodeSelected) {
          this.onNodeSelected(clicked);
        }
      } else {
        this.isDragging = true;
        this.dragStartX = e.clientX - this.panX;
        this.dragStartY = e.clientY - this.panY;
      }
    });

    window.addEventListener('mousemove', e => {
      if (this.isDragging) {
        this.panX = e.clientX - this.dragStartX;
        this.panY = e.clientY - this.dragStartY;
      } else {
        const pos = this.getCanvasCoords(e);
        this.hoveredNode = this.findNodeAt(pos.x, pos.y);
      }
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    this.canvas.addEventListener('wheel', e => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
      this.zoom = Math.max(0.4, Math.min(2.5, this.zoom * zoomFactor));
    });
  }

  getCanvasCoords(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left - this.panX) / this.zoom,
      y: (e.clientY - rect.top - this.panY) / this.zoom
    };
  }

  findNodeAt(x, y) {
    for (let i = this.nodes.length - 1; i >= 0; i--) {
      const n = this.nodes[i];
      const dx = n.x - x;
      const dy = n.y - y;
      if (Math.sqrt(dx * dx + dy * dy) <= (n.radius || 18) + 6) {
        return n;
      }
    }
    return null;
  }

  startAnimationLoop() {
    const render = () => {
      this.draw();
      this.animFrameId = requestAnimationFrame(render);
    };
    render();
  }

  draw() {
    if (!this.canvas) return;
    const parent = this.canvas.parentElement;
    if (parent && parent.clientWidth > 0 && parent.clientHeight > 0) {
      if (this.canvas.width !== parent.clientWidth || this.canvas.height !== parent.clientHeight) {
        this.canvas.width = parent.clientWidth;
        this.canvas.height = parent.clientHeight;
        if (this.nodes.length > 0) {
          this.calculateHierarchicalLayout();
        }
      }
    }

    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    this.ctx.save();
    this.ctx.translate(this.panX, this.panY);
    this.ctx.scale(this.zoom, this.zoom);

    // Draw connecting edges
    this.edges.forEach(edge => {
      const source = this.nodeMap.get(edge.source_id);
      const target = this.nodeMap.get(edge.target_id);
      if (source && target) {
        this.drawEdge(source, target, edge);
      }
    });

    // Draw graph nodes
    this.nodes.forEach(node => {
      this.drawNode(node);
    });

    // Pulse highlight on the newest node
    const newest = this.newNodeHighlight ? this.nodeMap.get(this.newNodeHighlight) : null;
    if (newest) {
      const time = performance.now() / 1000;
      const pulse = (Math.sin(time * 2.5) + 1) / 2;
      this.ctx.beginPath();
      this.ctx.arc(newest.x, newest.y, newest.radius + 6 + pulse * 6, 0, Math.PI * 2);
      this.ctx.strokeStyle = `rgba(46, 204, 113, ${0.5 - pulse * 0.3})`;
      this.ctx.lineWidth = 2;
      this.ctx.stroke();
    }

    this.ctx.restore();
  }

  drawEdge(source, target, edge) {
    const isLight = document.documentElement.classList.contains('theme-light');
    const isContaminated = source.is_stale || target.is_stale || source.status === 'INVALIDATED' || this.blastRadiusSet.has(source.id) || this.blastRadiusSet.has(target.id);

    this.ctx.beginPath();
    this.ctx.moveTo(source.x, source.y);
    this.ctx.lineTo(target.x, target.y);

    if (isContaminated) {
      this.ctx.strokeStyle = isLight ? 'rgba(190, 18, 60, 0.9)' : 'rgba(225, 29, 72, 0.85)';
      this.ctx.lineWidth = 2.5;
      this.ctx.setLineDash([4, 4]);
    } else {
      this.ctx.strokeStyle = isLight ? 'rgba(0, 0, 0, 0.22)' : 'rgba(255, 255, 255, 0.18)';
      this.ctx.lineWidth = 1.5;
      this.ctx.setLineDash([]);
    }

    this.ctx.stroke();
    this.ctx.setLineDash([]);

    // Arrowhead pointing from source to target
    const angle = Math.atan2(target.y - source.y, target.x - source.x);
    const headLen = 7;
    const targetEdgeX = target.x - Math.cos(angle) * (target.radius + 2);
    const targetEdgeY = target.y - Math.sin(angle) * (target.radius + 2);

    this.ctx.beginPath();
    this.ctx.moveTo(targetEdgeX, targetEdgeY);
    this.ctx.lineTo(
      targetEdgeX - headLen * Math.cos(angle - Math.PI / 6),
      targetEdgeY - headLen * Math.sin(angle - Math.PI / 6)
    );
    this.ctx.lineTo(
      targetEdgeX - headLen * Math.cos(angle + Math.PI / 6),
      targetEdgeY - headLen * Math.sin(angle + Math.PI / 6)
    );
    this.ctx.fillStyle = isContaminated ? (isLight ? '#BE123C' : '#E11D48') : (isLight ? 'rgba(0, 0, 0, 0.35)' : 'rgba(255, 255, 255, 0.35)');
    this.ctx.fill();
  }

  drawNode(node) {
    const isLight = document.documentElement.classList.contains('theme-light');
    const isSelected = this.selectedNode && this.selectedNode.id === node.id;
    const isHovered = this.hoveredNode && this.hoveredNode.id === node.id;
    const isStale = node.is_stale || node.status === 'INVALIDATED' || this.blastRadiusSet.has(node.id);

    let baseColor = isLight ? '#15803D' : '#2ECC71'; // Healthy green Fact
    if (node.kind === 'AGENT') baseColor = isLight ? '#095ec4' : '#0566d9'; // Blue Agent
    else if (node.kind === 'DECISION') baseColor = isLight ? '#7E22CE' : '#A855F7'; // Purple Decision
    else if (node.kind === 'ARTIFACT') baseColor = isLight ? '#E04B2F' : '#F05638'; // Vermilion Artifact
    else if (node.kind === 'EVIDENCE') baseColor = isLight ? '#B45309' : '#F59E0B'; // Amber Evidence
    else if (node.kind === 'MESSAGE') baseColor = isLight ? '#B45309' : '#F59E0B'; // Amber source message

    if (node.status === 'SUPERSEDED') baseColor = isLight ? '#9AA3B2' : '#5A6270';
    if (isStale) baseColor = isLight ? '#BE123C' : '#E11D48';

    // Outer glow halo for contaminated nodes
    if (isStale) {
      this.ctx.beginPath();
      this.ctx.arc(node.x, node.y, node.radius + 8, 0, Math.PI * 2);
      this.ctx.fillStyle = isLight ? 'rgba(190, 18, 60, 0.25)' : 'rgba(225, 29, 72, 0.3)';
      this.ctx.fill();
    }

    // Selected or hovered outer ring
    if (isSelected || isHovered) {
      this.ctx.beginPath();
      this.ctx.arc(node.x, node.y, node.radius + 5, 0, Math.PI * 2);
      this.ctx.strokeStyle = isLight ? '#1C1E23' : '#EDEDED';
      this.ctx.lineWidth = 2.5;
      this.ctx.stroke();
    }

    // Node body
    this.ctx.beginPath();
    this.ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    this.ctx.fillStyle = baseColor;
    this.ctx.fill();

    this.ctx.strokeStyle = isLight ? 'rgba(0, 0, 0, 0.15)' : 'rgba(255, 255, 255, 0.35)';
    this.ctx.lineWidth = 1.5;
    this.ctx.stroke();

    // Clean node label badge
    const labelText = this.getCleanShortLabel(node);
    this.ctx.font = '11px "JetBrains Mono", monospace';
    this.ctx.textAlign = 'center';

    // Draw clean background tag for readability
    const textWidth = this.ctx.measureText(labelText).width;
    const tagX = node.x - textWidth / 2 - 4;
    const tagY = node.y + node.radius + 6;
    
    this.ctx.fillStyle = isLight ? 'rgba(248, 246, 240, 0.95)' : 'rgba(13, 14, 16, 0.85)';
    this.ctx.fillRect(tagX, tagY, textWidth + 8, 16);
    this.ctx.strokeStyle = isLight ? 'rgba(216, 210, 194, 0.9)' : 'rgba(42, 46, 53, 0.7)';
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(tagX, tagY, textWidth + 8, 16);

    this.ctx.fillStyle = isStale ? (isLight ? '#BE123C' : '#ff8da1') : (isLight ? '#1C1E23' : '#CBD5E1');
    this.ctx.fillText(labelText, node.x, tagY + 12);
  }
}
