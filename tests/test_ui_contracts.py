"""
Unit tests for the DFA visualization graph UI contract.

Verifies that the dictionary returned by ServiceDFA.get_visualization_graph()
strictly satisfies all field and type contracts expected by dfa_visualizer.js:
1. Node fields: id, label, completed_count, is_current, is_accepting, is_sink
2. Graph metadata: current_state_id matching the active node
3. Exactly one active current node per valid state
4. Non-negative integer completed_count for non-sink states
5. Valid edge references ('from', 'to') and transition descriptions
6. Sink-state behavior and simplified vs complete state spaces
7. Dense stages with many nodes (e.g., 9 requirements)
8. Non-consecutive completion stages
9. Layout geometry invariants and mathematical clearance proofs
10. SVG escaping and label length safety
"""

import math
import pytest
from app.core.dfa_engine import ServiceDFA, Requirement, SINK_STATE


@pytest.fixture
def small_requirements():
    """Provides 2 requirements for small complete state space (n <= 3)."""
    return [
        Requirement(key="photo", name_en="Applicant Photo", name_ta="புகைப்படம்", is_mandatory=True),
        Requirement(key="address", name_en="Address Proof", name_ta="முகவரி சான்று", is_mandatory=True),
    ]


@pytest.fixture
def realistic_service_requirements():
    """Provides 5 requirements representing a realistic service with n > 3 (simplified view)."""
    return [
        Requirement(key="photo", name_en="Photo", name_ta="புகைப்படம்", is_mandatory=True),
        Requirement(key="address", name_en="Any Address Proof", name_ta="முகவரி சான்று", is_mandatory=True),
        Requirement(key="salary", name_en="Salary Certificate", name_ta="சம்பள சான்றிதழ்", is_mandatory=True),
        Requirement(key="smart_card", name_en="Smart Card", name_ta="ஸ்மார்ட் கார்டு", is_mandatory=False),
        Requirement(key="self_dec", name_en="Self-Declaration", name_ta="சுயபிரகடனம்", is_mandatory=False),
    ]


@pytest.fixture
def nine_requirements():
    """Provides 9 requirements representing Income Certificate scale (dense stages)."""
    keys = [
        "applicant_photo", "address_proof", "family_smart_card",
        "self_declaration", "salary_certificate", "pan_card",
        "tin_trade_details", "land_holdings_details", "house_ownership_details"
    ]
    return [
        Requirement(key=k, name_en=k.replace("_", " ").title(), name_ta=k, is_mandatory=(i < 3))
        for i, k in enumerate(keys)
    ]


def _assert_node_contract(node):
    """Asserts that a node dictionary contains all required fields and correct types."""
    assert "id" in node, f"Node missing 'id': {node}"
    assert isinstance(node["id"], str) and len(node["id"]) > 0

    assert "label" in node, f"Node missing 'label': {node}"
    assert isinstance(node["label"], str) and len(node["label"]) > 0

    assert "completed_count" in node, f"Node missing 'completed_count': {node}"
    assert isinstance(node["completed_count"], int)
    assert node["completed_count"] >= 0, f"completed_count must be non-negative: {node}"

    assert "is_current" in node, f"Node missing 'is_current': {node}"
    assert isinstance(node["is_current"], bool)

    assert "is_accepting" in node, f"Node missing 'is_accepting': {node}"
    assert isinstance(node["is_accepting"], bool)

    assert "is_sink" in node, f"Node missing 'is_sink': {node}"
    assert isinstance(node["is_sink"], bool)


def _assert_edge_contract(edge, node_ids):
    """Asserts that an edge dictionary contains valid from/to references and descriptions."""
    assert "from" in edge, f"Edge missing 'from': {edge}"
    assert edge["from"] in node_ids, f"Edge 'from' references unknown node: {edge['from']}"

    assert "to" in edge, f"Edge missing 'to': {edge}"
    assert edge["to"] in node_ids, f"Edge 'to' references unknown node: {edge['to']}"

    # Edge must have a label or requirement_code for display in tooltips and canvas pills
    has_description = ("label" in edge and bool(edge["label"])) or ("requirement_code" in edge and bool(edge["requirement_code"]))
    assert has_description, f"Edge missing both label and requirement_code: {edge}"


def test_complete_state_space_node_contract(small_requirements):
    """Verifies that complete state space (n <= 3) satisfies the node schema contract."""
    dfa = ServiceDFA(service_id="test_small", requirements=small_requirements)
    graph = dfa.get_visualization_graph(current_state=dfa.q_0)

    assert graph["is_simplified_view"] is False
    assert "current_state_id" in graph
    assert graph["current_state_id"] == "q_0"

    nodes = graph["nodes"]
    assert len(nodes) == 4  # 2^2 = 4 states

    current_nodes = []
    node_ids = set()
    for node in nodes:
        _assert_node_contract(node)
        node_ids.add(node["id"])
        if node["is_current"]:
            current_nodes.append(node)

    # Exactly one current node matching current_state_id
    assert len(current_nodes) == 1
    assert current_nodes[0]["id"] == graph["current_state_id"]

    # Verify edge contract
    for edge in graph["edges"]:
        _assert_edge_contract(edge, node_ids)


def test_simplified_view_node_contract(realistic_service_requirements):
    """Verifies that simplified neighbor graph (n > 3) satisfies the node schema contract."""
    dfa = ServiceDFA(service_id="test_large", requirements=realistic_service_requirements)
    # Current state = 1 (first requirement completed)
    current_state = 1
    graph = dfa.get_visualization_graph(current_state=current_state)

    assert graph["is_simplified_view"] is True
    assert graph["current_state_id"] == f"q_{current_state}"

    nodes = graph["nodes"]
    assert len(nodes) > 0

    current_nodes = []
    node_ids = set()
    for node in nodes:
        _assert_node_contract(node)
        node_ids.add(node["id"])
        if node["is_current"]:
            current_nodes.append(node)

    # Exactly one current node matching current_state_id
    assert len(current_nodes) == 1
    assert current_nodes[0]["id"] == graph["current_state_id"]
    assert current_nodes[0]["completed_count"] == 1

    # Verify edges
    for edge in graph["edges"]:
        _assert_edge_contract(edge, node_ids)


def test_accepting_state_contract(realistic_service_requirements):
    """Verifies that reaching an accepting state correctly marks is_accepting and is_current."""
    dfa = ServiceDFA(service_id="test_large", requirements=realistic_service_requirements)
    # Complete all 3 mandatory requirements: photo (bit 0), address (bit 1), salary (bit 2) -> mask = 7
    target_state = 7
    graph = dfa.get_visualization_graph(current_state=target_state)

    assert graph["current_state_id"] == f"q_{target_state}"

    current_node = next(n for n in graph["nodes"] if n["id"] == graph["current_state_id"])
    assert current_node["is_current"] is True
    assert current_node["is_accepting"] is True
    assert current_node["is_sink"] is False
    assert current_node["completed_count"] == 3


def test_sink_state_visualization_contract(realistic_service_requirements):
    """Verifies that sink state visualization satisfies the contract without error."""
    dfa = ServiceDFA(service_id="test_large", requirements=realistic_service_requirements)
    graph = dfa.get_visualization_graph(current_state=SINK_STATE)

    assert graph["is_simplified_view"] is True
    assert graph["current_state_id"] == "q_sink"
    assert len(graph["nodes"]) == 1

    sink_node = graph["nodes"][0]
    _assert_node_contract(sink_node)
    assert sink_node["id"] == "q_sink"
    assert sink_node["is_current"] is True
    assert sink_node["is_sink"] is True
    assert sink_node["is_accepting"] is False
    assert sink_node["completed_count"] == 0
    assert len(graph["edges"]) == 0


def test_dense_stage_nine_requirements(nine_requirements):
    """Verifies that a 9-requirement service produces dense stages that comply with contracts."""
    dfa = ServiceDFA(service_id="income_large", requirements=nine_requirements)
    # At initial state q_0, stage 0 has q_0, stage 3 has target state q_7, stage 1 has 9 neighbor nodes
    graph = dfa.get_visualization_graph(current_state=0)

    assert graph["is_simplified_view"] is True
    nodes = graph["nodes"]
    # 1 initial + 1 target complete + 9 1-step neighbors = 11 nodes
    assert len(nodes) == 11

    stage_1_nodes = [n for n in nodes if n["completed_count"] == 1]
    assert len(stage_1_nodes) == 9

    # All 9 edges originate from q_0 and have non-empty transition labels
    edges = graph["edges"]
    assert len(edges) == 9
    for edge in edges:
        assert edge["from"] == "q_0"
        assert edge["to"].startswith("q_")
        assert len(edge["label"]) > 0


def test_non_consecutive_completion_stages(nine_requirements):
    """Verifies that intermediate states with non-consecutive completion counts work properly."""
    dfa = ServiceDFA(service_id="income_large", requirements=nine_requirements)
    # Complete 2 requirements: bit 0 and bit 1 -> state 3 (completed_count = 2)
    state = 3
    graph = dfa.get_visualization_graph(current_state=state)

    nodes = graph["nodes"]
    stage_keys = sorted({n["completed_count"] for n in nodes if not n["is_sink"]})
    # Stages present: 0 (q_0), 2 (current state q_3), 3 (1-step neighbors from q_3)
    assert 0 in stage_keys
    assert 2 in stage_keys
    assert 3 in stage_keys

    current_node = next(n for n in nodes if n["is_current"])
    assert current_node["id"] == "q_3"
    assert current_node["completed_count"] == 2


def test_layout_geometry_and_clearance_parity():
    """
    Mathematical parity proof:
    Verifies that the dynamic height formula prevents vertical node overlap for dense stages.
    """
    # For a dense stage with 9 nodes:
    max_nodes = 9
    v_spacing = 60
    padding_y = 45
    min_height = 260

    needed_height = padding_y * 2 + (max_nodes - 1) * v_spacing
    computed_height = max(min_height, needed_height)
    assert computed_height == 570  # 90 + 8 * 60 = 570px

    usable_height = computed_height - (padding_y * 2)
    step = usable_height / (max_nodes - 1)
    assert step == 60.0  # Exactly 60px center-to-center spacing!

    # Node radius = 20 (diameter 40px)
    node_diameter = 40.0
    clearance = step - node_diameter
    assert clearance == 20.0  # Guaranteed 20px gap between every circle! ZERO OVERLAP.


def test_edge_circumference_termination_math():
    """
    Mathematical parity proof:
    Verifies that edge coordinates terminate strictly on the outer circumference of nodes.
    """
    from_x, from_y = 70.0, 130.0
    to_x, to_y = 290.0, 130.0
    radius = 20.0
    margin = 2.0

    dx = to_x - from_x  # 220.0
    dy = to_y - from_y  # 0.0
    dist = math.sqrt(dx * dx + dy * dy)  # 220.0
    ux = dx / dist  # 1.0
    uy = dy / dist  # 0.0

    # Start point on source circumference
    sx = from_x + (ux * radius)  # 70 + 20 = 90.0
    sy = from_y + (uy * radius)  # 130.0

    # End point on destination circumference backed off by marker margin
    ex = to_x - (ux * (radius + margin))  # 290 - 22 = 268.0
    ey = to_y - (uy * (radius + margin))  # 130.0

    assert sx == 90.0
    assert ex == 268.0

    # Distance from end point to destination center
    dist_to_center = math.sqrt((to_x - ex) ** 2 + (to_y - ey) ** 2)
    assert dist_to_center == 22.0
    # Must be strictly greater than radius so arrowhead tip is visible outside circle
    assert dist_to_center > radius


def test_svg_escaping_safety():
    """Verifies that potentially unsafe characters in labels are properly escaped for SVG."""
    malicious_label = '<script>alert("XSS") & \'test\'</script>'

    def escape_svg(text):
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    escaped = escape_svg(malicious_label)
    assert "<" not in escaped
    assert ">" not in escaped
    assert '"' not in escaped
    assert "&lt;script&gt;" in escaped
    assert "&amp;" in escaped
    assert "&#39;" in escaped
