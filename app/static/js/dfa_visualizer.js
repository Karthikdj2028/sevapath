/**
 * SevaPath - Interactive Deterministic Finite Automaton (DFA) Visualizer
 * Pure Vanilla JavaScript & SVG (Zero external heavy dependencies)
 * 
 * Accurately renders actual states and transitions computed by Python backend:
 * - Nodes: States q in Q with satisfied bitmasks and readiness
 * - Edges: Deterministic transitions delta(q, COMPLETE_r_i) = q'
 * - Accepting States F: Double concentric circle (formal automata convention)
 * - Current State: Highlighted active node with transition pulse
 */

class DFAVisualizer {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.options = Object.assign({
      width: 780,
      height: 250,
      nodeRadius: 24,
    }, options);
  }

  render(graphData) {
    if (!this.container || !graphData || !graphData.nodes) return;

    const { nodes, edges, current_state, is_accepting, is_simplified_view, view_description } = graphData;
    const { width, height, nodeRadius } = this.options;

    // Group nodes by stage (satisfied_count) for hierarchical topological layout
    const stages = {};
    let maxStage = 0;

    nodes.forEach(node => {
      const stage = node.is_sink ? -1 : (node.satisfied_count || 0);
      if (!stages[stage]) stages[stage] = [];
      stages[stage].push(node);
      if (stage > maxStage) maxStage = stage;
    });

    // Compute coordinates for each node
    const stageKeys = Object.keys(stages).map(Number).sort((a, b) => a - b);
    const nodeCoords = {};

    const paddingX = 60;
    const paddingY = 45;
    const usableWidth = width - (paddingX * 2);
    const usableHeight = height - (paddingY * 2);

    stageKeys.forEach(stageKey => {
      const stageNodes = stages[stageKey];
      const count = stageNodes.length;
      
      // X coordinate
      let xRatio;
      if (stageKey === -1) {
        xRatio = 0.5; // Sink at bottom center
      } else {
        xRatio = maxStage === 0 ? 0.5 : (stageKey / maxStage);
      }
      const x = paddingX + (xRatio * usableWidth);

      // Y coordinate distributed evenly within stage column
      stageNodes.forEach((node, idx) => {
        let y;
        if (stageKey === -1) {
          y = height - 30; // Sink position
        } else if (count === 1) {
          y = height / 2;
        } else {
          const step = usableHeight / (count - 1);
          y = paddingY + (idx * step);
        }
        nodeCoords[node.id] = { x, y };
      });
    });

    // Build SVG markup
    let svgHtml = `
      <svg viewBox="0 0 ${width} ${height}" class="w-100 h-auto dfa-svg" style="max-height: 280px; font-family: inherit;">
        <defs>
          <!-- Arrow marker standard -->
          <marker id="arrow" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="#94a3b8" />
          </marker>
          <!-- Active transition arrow marker -->
          <marker id="arrow-active" viewBox="0 0 10 10" refX="28" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 1 L 10 5 L 0 9 z" fill="#2563eb" />
          </marker>
        </defs>
    `;

    // 1. Render Edges (Transitions)
    edges.forEach(edge => {
      const from = nodeCoords[edge.from];
      const to = nodeCoords[edge.to];
      if (!from || !to) return;

      const isActive = edge.is_active_transition;
      const strokeColor = isActive ? "#2563eb" : "#cbd5e1";
      const strokeWidth = isActive ? "2.5" : "1.5";
      const marker = isActive ? "url(#arrow-active)" : "url(#arrow)";
      const strokeDash = edge.is_mandatory === false ? "4,4" : "";

      // Quadratic curve for nicer edge separation if same Y
      let pathD = `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
      if (from.x === to.x && from.y !== to.y) {
        const midY = (from.y + to.y) / 2;
        pathD = `M ${from.x} ${from.y} Q ${from.x + 25} ${midY} ${to.x} ${to.y}`;
      }

      svgHtml += `
        <path d="${pathD}" 
              fill="none" 
              stroke="${strokeColor}" 
              stroke-width="${strokeWidth}" 
              stroke-dasharray="${strokeDash}"
              marker-end="${marker}">
          <title>delta(${edge.from}, ${edge.symbol}) -> ${edge.to}</title>
        </path>
      `;
    });

    // 2. Render Nodes (States)
    nodes.forEach(node => {
      const coord = nodeCoords[node.id];
      if (!coord) return;

      const isCurrent = node.id === current_state;
      const isAccept = node.is_accepting;
      const isInitial = node.is_initial;
      const isSink = node.is_sink;

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

      // Main node group
      svgHtml += `<g class="dfa-node" data-id="${node.id}" style="cursor: pointer;">`;

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
          <title>State ${node.label} | Bits: ${node.bits} | Readiness: ${node.readiness}%</title>
        </circle>
      `;

      // Accepting state double-circle convention
      if (isAccept) {
        svgHtml += `
          <circle cx="${coord.x}" cy="${coord.y}" r="${nodeRadius - 4}" fill="none" stroke="${stroke}" stroke-width="1.5" />
        `;
      }

      // Initial state start pointer arrow
      if (isInitial) {
        svgHtml += `
          <path d="M ${coord.x - nodeRadius - 16} ${coord.y} L ${coord.x - nodeRadius} ${coord.y}" stroke="#0f172a" stroke-width="2" marker-end="url(#arrow)"/>
        `;
      }

      // State text label (e.g. q0, q3)
      svgHtml += `
        <text x="${coord.x}" y="${coord.y + 4}" font-size="11" font-weight="${isCurrent ? 'bold' : '600'}" text-anchor="middle" fill="${isCurrent ? stroke : '#1e293b'}">
          ${node.label.replace(' (Start)', '')}
        </text>
      `;

      svgHtml += `</g>`;
    });

    svgHtml += `</svg>`;

    // Add view description banner
    const badgeClass = is_simplified_view ? "badge bg-warning-subtle text-dark border border-warning" : "badge bg-info-subtle text-dark border border-info";
    const headerHtml = `
      <div class="d-flex justify-content-between align-items-center mb-2 px-1">
        <span class="${badgeClass} small">
          ℹ️ ${view_description}
        </span>
        <span class="small text-muted">
          Active: <strong class="text-primary">${graphData.current_state === -1 ? 'q_sink (Error)' : 'q_' + graphData.current_state}</strong>
          ${is_accepting ? ' (Accepting F ✓)' : ''}
        </span>
      </div>
    `;

    this.container.innerHTML = headerHtml + svgHtml;
  }
}

window.DFAVisualizer = DFAVisualizer;
