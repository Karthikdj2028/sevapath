/**
 * SevaPath - Interactive Deterministic Finite Automaton (DFA) Visualizer
 * Pure Vanilla JavaScript & SVG (Zero external heavy dependencies)
 * 
 * Accurately renders actual states and transitions computed by Python backend:
 * - Dynamic vertical layout avoiding node collisions (min 55-65px center-to-center)
 * - True circumference edge termination with high-contrast directional arrowheads
 * - Visible canvas transition labels with contrasting background pills
 * - Distinct styling for Current, Accepting (F), and Sink (q_sink) states
 */

class DFAVisualizer {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.options = Object.assign({
      width: 780,
      height: 260,
      nodeRadius: 20,
      verticalSpacing: 60,
      horizontalSpacing: 220,
      paddingX: 70,
      paddingY: 45,
    }, options);
  }

  /**
   * Safely escapes text content for inclusion in SVG markup.
   */
  static escapeSvg(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * Calculates layout coordinates and dynamic canvas dimensions.
   * Ensures nodes in dense stages are never positioned at overlapping coordinates.
   */
  static computeLayout(graphData, options) {
    const nodes = Array.isArray(graphData.nodes) ? graphData.nodes : [];
    const minHeight = Math.max(260, options.height || 260);
    const minWidth = Math.max(480, options.width || 480);
    const paddingX = options.paddingX || 70;
    const paddingY = options.paddingY || 45;
    const vSpacing = options.verticalSpacing || 60;
    const hSpacing = options.horizontalSpacing || 220;

    // Group nodes by completed_count
    const stages = {};
    let hasSink = false;

    nodes.forEach(node => {
      const isSink = Boolean(node.is_sink);
      if (isSink) {
        hasSink = true;
        if (!stages[-1]) stages[-1] = [];
        stages[-1].push(node);
      } else {
        const completed = Number.isInteger(node.completed_count) && node.completed_count >= 0
          ? node.completed_count
          : 0;
        if (!stages[completed]) stages[completed] = [];
        stages[completed].push(node);
      }
    });

    // Determine max nodes in any single standard stage
    let maxNodesInStage = 1;
    const regularStageKeys = Object.keys(stages)
      .map(Number)
      .filter(k => k >= 0)
      .sort((a, b) => a - b);

    regularStageKeys.forEach(k => {
      if (stages[k].length > maxNodesInStage) {
        maxNodesInStage = stages[k].length;
      }
    });

    // Calculate dynamic canvas height to guarantee no vertical circle overlap
    const neededRegularHeight = paddingY * 2 + (maxNodesInStage - 1) * vSpacing;
    const sinkAllowance = hasSink ? 70 : 0;
    const computedHeight = Math.max(minHeight, neededRegularHeight + sinkAllowance);

    // Calculate dynamic canvas width to ensure horizontal clearance between stages
    const numRegularStages = regularStageKeys.length;
    const neededWidth = numRegularStages <= 1
      ? minWidth
      : paddingX * 2 + (numRegularStages - 1) * hSpacing;
    const computedWidth = Math.max(minWidth, neededWidth);

    const usableWidth = computedWidth - (paddingX * 2);
    const usableRegularHeight = computedHeight - (paddingY * 2) - sinkAllowance;

    // Compute coordinate mapping: node.id -> { x, y }
    const nodeCoords = {};

    regularStageKeys.forEach((stageKey, stageIdx) => {
      const stageNodes = stages[stageKey];
      const count = stageNodes.length;

      // X coordinate spaced evenly across regular stages
      let xRatio = 0.5;
      if (numRegularStages > 1) {
        xRatio = stageIdx / (numRegularStages - 1);
      }
      const x = paddingX + (xRatio * usableWidth);

      // Y coordinates distributed evenly within column with guaranteed clearance
      stageNodes.forEach((node, idx) => {
        let y;
        if (count === 1) {
          y = paddingY + (usableRegularHeight / 2);
        } else {
          const step = usableRegularHeight / (count - 1);
          y = paddingY + (idx * step);
        }
        nodeCoords[node.id] = { x, y };
      });
    });

    // Position sink state at bottom center if present
    if (hasSink && stages[-1]) {
      stages[-1].forEach((node, idx) => {
        const sinkCount = stages[-1].length;
        const sinkStep = 80;
        const startX = (computedWidth / 2) - ((sinkCount - 1) * sinkStep / 2);
        const x = startX + (idx * sinkStep);
        const y = computedHeight - 35;
        nodeCoords[node.id] = { x, y };
      });
    }

    return {
      nodeCoords,
      computedWidth,
      computedHeight,
      regularStageKeys,
      maxNodesInStage,
      hasSink
    };
  }

  /**
   * Computes edge start and end coordinates clipped to node circumferences.
   * Ensures directional arrowheads terminate outside the destination circle.
   */
  static calculateEdgeGeometry(fromCoord, toCoord, sourceRadius, targetRadius, margin = 2) {
    const dx = toCoord.x - fromCoord.x;
    const dy = toCoord.y - fromCoord.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    // Guard against identical coordinates or zero-distance loops
    if (dist <= (sourceRadius + targetRadius) || dist < 1e-4) {
      return {
        isLoop: true,
        pathD: `M ${fromCoord.x} ${fromCoord.y - sourceRadius} C ${fromCoord.x - 30} ${fromCoord.y - sourceRadius - 35}, ${fromCoord.x + 30} ${fromCoord.y - sourceRadius - 35}, ${fromCoord.x + 8} ${fromCoord.y - sourceRadius - 2}`,
        mx: fromCoord.x,
        my: fromCoord.y - sourceRadius - 38
      };
    }

    const ux = dx / dist;
    const uy = dy / dist;

    // Start on outer circumference of source node
    const sx = fromCoord.x + (ux * sourceRadius);
    const sy = fromCoord.y + (uy * sourceRadius);

    // End on outer circumference of destination node (backed off by marker margin)
    const ex = toCoord.x - (ux * (targetRadius + margin));
    const ey = toCoord.y - (uy * (targetRadius + margin));

    // Midpoint for transition text label
    const mx = (sx + ex) / 2;
    const my = (sy + ey) / 2;

    return {
      isLoop: false,
      sx, sy, ex, ey, mx, my,
      pathD: `M ${sx} ${sy} L ${ex} ${ey}`
    };
  }

  render(graphData) {
    if (!this.container) return;
    if (!graphData || !Array.isArray(graphData.nodes) || graphData.nodes.length === 0) {
      this.container.innerHTML = "";
      return;
    }

    const { nodes, is_simplified_view, view_description, current_state_id } = graphData;
    const edges = Array.isArray(graphData.edges) ? graphData.edges : [];
    const nodeRadius = this.options.nodeRadius || 20;

    // 1. Compute dynamic non-overlapping layout
    const layout = DFAVisualizer.computeLayout(graphData, this.options);
    const { nodeCoords, computedWidth, computedHeight } = layout;

    // 2. SVG Header with userSpaceOnUse arrowhead marker
    let svgHtml = `
      <svg viewBox="0 0 ${computedWidth} ${computedHeight}"
           class="w-100 h-auto dfa-svg"
           style="max-height: 540px; font-family: inherit; display: block;"
           role="img"
           aria-label="Deterministic Finite Automaton Transition Graph">
        <defs>
          <!-- High-contrast directional arrowhead terminating at node boundary -->
          <marker id="arrow"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="8"
                  markerHeight="8"
                  orient="auto"
                  markerUnits="userSpaceOnUse">
            <path d="M 0 1 L 9 5 L 0 9 L 2 5 z" fill="#475569" />
          </marker>
        </defs>
    `;

    // 3. Render Edges with visible transition label pills
    edges.forEach(edge => {
      const from = nodeCoords[edge.from];
      const to = nodeCoords[edge.to];
      if (!from || !to) return;

      const geom = DFAVisualizer.calculateEdgeGeometry(from, to, nodeRadius, nodeRadius, 2);
      const rawDescription = edge.label || edge.requirement_code || "";
      const displayLabel = rawDescription.length > 20
        ? rawDescription.slice(0, 19) + "…"
        : rawDescription;
      const escapedLabel = DFAVisualizer.escapeSvg(displayLabel);
      const edgeTitle = rawDescription
        ? `${edge.from} -> ${edge.to}: ${rawDescription}`
        : `${edge.from} -> ${edge.to}`;

      // Transition edge line
      svgHtml += `
        <g class="dfa-edge">
          <path d="${geom.pathD}"
                fill="none"
                stroke="#64748b"
                stroke-width="1.8"
                marker-end="url(#arrow)">
            <title>${DFAVisualizer.escapeSvg(edgeTitle)}</title>
          </path>
      `;

      // Visible transition label pill (rendered at edge midpoint)
      if (displayLabel) {
        const textWidth = Math.max(34, displayLabel.length * 6.5 + 10);
        const rectX = geom.mx - (textWidth / 2);
        const rectY = geom.my - 8;

        svgHtml += `
          <g class="dfa-edge-label" transform="translate(0, 0)">
            <rect x="${rectX}" y="${rectY}" width="${textWidth}" height="16" rx="4"
                  fill="#ffffff" stroke="#94a3b8" stroke-width="0.8" opacity="0.96"/>
            <text x="${geom.mx}" y="${geom.my + 4}"
                  font-size="9.5" font-weight="600" text-anchor="middle" fill="#0f172a">
              ${escapedLabel}
            </text>
            <title>${DFAVisualizer.escapeSvg(edgeTitle)}</title>
          </g>
        `;
      }

      svgHtml += `</g>`;
    });

    // 4. Render Nodes (States)
    let currentNodeObj = null;

    nodes.forEach(node => {
      const coord = nodeCoords[node.id];
      if (!coord) return;

      const isCurrent = node.is_current === true || (Boolean(current_state_id) && node.id === current_state_id);
      if (isCurrent && !currentNodeObj) {
        currentNodeObj = node;
      }
      const isAccept = Boolean(node.is_accepting);
      const isSink = Boolean(node.is_sink);

      let fill = "#ffffff";
      let stroke = "#64748b";
      let strokeWidth = 2;

      if (isCurrent) {
        fill = isAccept ? "#ecfdf5" : "#eff6ff";
        stroke = isAccept ? "#059669" : "#2563eb";
        strokeWidth = 3.5;
      } else if (isAccept) {
        fill = "#f0fdf4";
        stroke = "#10b981";
      } else if (isSink) {
        fill = "#fef2f2";
        stroke = "#ef4444";
      }

      // Build safe tooltip using verified fields
      const count = Number.isInteger(node.completed_count) && node.completed_count >= 0 ? node.completed_count : 0;
      let tooltip = `State: ${node.label || node.id}`;
      if (isSink) {
        tooltip += " | Rejection State";
      } else {
        tooltip += ` | Documents Ready: ${count}`;
        if (isAccept) {
          tooltip += " | Target Complete (Accepting)";
        }
        if (isCurrent) {
          tooltip += " | Active State";
        }
      }

      // Main node group
      svgHtml += `<g class="dfa-node" data-id="${DFAVisualizer.escapeSvg(node.id)}" style="cursor: pointer;">`;

      // Highlight pulse halo for active current state
      if (isCurrent) {
        svgHtml += `
          <circle cx="${coord.x}" cy="${coord.y}" r="${nodeRadius + 6}" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-dasharray="3,3" opacity="0.7">
            <animate attributeName="r" values="${nodeRadius + 3};${nodeRadius + 8};${nodeRadius + 3}" dur="2s" repeatCount="indefinite"/>
          </circle>
        `;
      }

      // Outer circle
      svgHtml += `
        <circle cx="${coord.x}" cy="${coord.y}" r="${nodeRadius}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}">
          <title>${DFAVisualizer.escapeSvg(tooltip)}</title>
        </circle>
      `;

      // Accepting state double-circle convention
      if (isAccept) {
        svgHtml += `
          <circle cx="${coord.x}" cy="${coord.y}" r="${nodeRadius - 4}" fill="none" stroke="${stroke}" stroke-width="1.5" />
        `;
      }

      // State text label (e.g. q0, q3)
      const cleanLabel = (node.label || node.id).replace(' (Start)', '');
      svgHtml += `
        <text x="${coord.x}" y="${coord.y + 4}" font-size="11" font-weight="${isCurrent ? 'bold' : '600'}" text-anchor="middle" fill="${isCurrent ? stroke : '#1e293b'}">
          ${DFAVisualizer.escapeSvg(cleanLabel)}
        </text>
      `;

      svgHtml += `</g>`;
    });

    svgHtml += `</svg>`;

    // 5. View description banner
    const isSimplified = Boolean(is_simplified_view);
    const badgeClass = isSimplified ? "badge bg-warning-subtle text-dark border border-warning" : "badge bg-info-subtle text-dark border border-info";
    const descText = view_description || (isSimplified ? "Simplified view" : "State space");
    const activeLabel = currentNodeObj ? (currentNodeObj.label || currentNodeObj.id) : (current_state_id || "q_0");
    const isCurrentAccepting = currentNodeObj ? Boolean(currentNodeObj.is_accepting) : false;

    const headerHtml = `
      <div class="d-flex justify-content-between align-items-center mb-2 px-1">
        <span class="${badgeClass} small">
          ℹ️ ${DFAVisualizer.escapeSvg(descText)}
        </span>
        <span class="small text-muted">
          Active: <strong class="text-primary">${DFAVisualizer.escapeSvg(activeLabel)}</strong>
          ${isCurrentAccepting ? ' (Accepting F ✓)' : ''}
        </span>
      </div>
    `;

    this.container.innerHTML = headerHtml + svgHtml;
  }
}

// Global and CommonJS export
window.DFAVisualizer = DFAVisualizer;
if (typeof module !== "undefined" && module.exports) {
  module.exports = DFAVisualizer;
}
