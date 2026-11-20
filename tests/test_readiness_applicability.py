"""
Pytest unit & integration tests for Citizen Applicability and DFA Readiness Engine.

Mathematically verifies:
- Empty-checklist protection: 0 applicable requirements yields 0.0% readiness and non-acceptance.
- Undetermined requirements block acceptance F even if all applicable items are completed.
- Dynamic session target mask M_session based strictly on citizen decisions.
- Not-applicable items do not block readiness.
- Nativity 5-year residence alternative proof as a single composite requirement.
- Multi-stage readiness labels: 'not_started', 'undetermined', 'in_progress', 'complete'.
- Absorbing sink state delta(q_sink, sigma) = q_sink under applicability transitions.
- Order independence of verification events.
"""

import pytest
from app.core.dfa_engine import ServiceDFA, Requirement, SINK_STATE


@pytest.fixture
def test_requirements():
    return [
        Requirement(key="doc_1", name_en="Photo", name_ta="படம்", is_mandatory=False),
        Requirement(key="doc_2", name_en="Address Proof", name_ta="முகவரி", is_mandatory=False),
        Requirement(key="doc_3", name_en="Birth Certificate", name_ta="பிறப்பு", is_mandatory=False),
        Requirement(key="doc_4_alt", name_en="5-Yr Residence", name_ta="வசிப்பிடம்", is_mandatory=True, logical_group="residence"),
    ]


def test_empty_checklist_protection(test_requirements):
    """
    CRITICAL READINESS REQUIREMENT:
    An empty checklist (no applicable requirements) must never show 100% readiness or accepting state.
    """
    # Citizen has not made decisions yet (all undetermined)
    applicability_all_undetermined = {r.key: "undetermined" for r in test_requirements}
    dfa = ServiceDFA("srv_test", test_requirements, citizen_applicability=applicability_all_undetermined)

    assert dfa.is_accepting(dfa.q_0) is False
    assert dfa.calculate_readiness(dfa.q_0) == 0.0
    assert dfa.get_readiness_stage(dfa.q_0) == "not_started"

    # Citizen marked all items as 'not_applicable'
    applicability_all_not_app = {r.key: "not_applicable" for r in test_requirements}
    dfa_none = ServiceDFA("srv_test", test_requirements, citizen_applicability=applicability_all_not_app)

    # Empty target mask must not cause immediate acceptance!
    assert dfa_none.target_mask == 0
    assert dfa_none.is_accepting(0) is False
    assert dfa_none.calculate_readiness(0) == 0.0


def test_undetermined_requirements_prevent_acceptance(test_requirements):
    """Verifies that having ANY requirement undetermined blocks accepting state."""
    # doc_1 is applicable and completed; doc_2 is undetermined
    applicability = {
        "doc_1": "applicable",
        "doc_2": "undetermined",
        "doc_3": "not_applicable",
        "doc_4_alt": "not_applicable",
    }
    dfa = ServiceDFA("srv_test", test_requirements, citizen_applicability=applicability)

    # Complete doc_1
    state = dfa.transition(dfa.q_0, "COMPLETE_doc_1")
    assert state > 0

    # Even though doc_1 is completed, doc_2 is undetermined -> cannot be accepting!
    assert dfa.is_accepting(state) is False
    assert dfa.get_readiness_stage(state) == "undetermined"


def test_not_applicable_items_do_not_block_readiness(test_requirements):
    """Verifies that items marked not_applicable are excluded from the target mask and do not block readiness."""
    # doc_1 is applicable; all others not applicable
    applicability = {
        "doc_1": "applicable",
        "doc_2": "not_applicable",
        "doc_3": "not_applicable",
        "doc_4_alt": "not_applicable",
    }
    dfa = ServiceDFA("srv_test", test_requirements, citizen_applicability=applicability)

    assert len(dfa.applicable_keys) == 1
    assert "doc_1" in dfa.applicable_keys

    # Before completion: 0%
    assert dfa.calculate_readiness(dfa.q_0) == 0.0
    assert dfa.is_accepting(dfa.q_0) is False

    # After completing doc_1: 100% and accepting!
    state = dfa.transition(dfa.q_0, "COMPLETE_doc_1")
    assert dfa.calculate_readiness(state) == 100.0
    assert dfa.is_accepting(state) is True
    assert dfa.get_readiness_stage(state) == "complete"


def test_switching_applicability_recalculates_target_mask(test_requirements):
    """Verifies that switching an item from not_applicable to applicable dynamically expands the target mask."""
    # Initially doc_1 is only applicable item
    app_1 = {"doc_1": "applicable", "doc_2": "not_applicable", "doc_3": "not_applicable", "doc_4_alt": "not_applicable"}
    dfa_1 = ServiceDFA("srv_test", test_requirements, citizen_applicability=app_1)
    mask_1 = dfa_1.target_mask

    # Citizen decides doc_2 is also applicable
    app_2 = {"doc_1": "applicable", "doc_2": "applicable", "doc_3": "not_applicable", "doc_4_alt": "not_applicable"}
    dfa_2 = ServiceDFA("srv_test", test_requirements, citizen_applicability=app_2)
    mask_2 = dfa_2.target_mask

    assert mask_2 > mask_1
    assert (mask_2 & (1 << dfa_2.key_to_index["doc_2"])) != 0


def test_nativity_composite_alternative_handling(client):
    """
    Verifies that Nativity Certificate's residence_proof_5yr is satisfied by completing
    the single composite item regardless of which alternative was selected.
    """
    init_res = client.get("/api/service/nativity-certificate/state")
    csrf = init_res.get_json()["csrf_token"]
    reqs = init_res.get_json()["requirements"]

    # Mark residence_proof_5yr as applicable with 'School Education Certificate' selected
    client.post(
        "/api/service/nativity-certificate/applicability",
        headers={"X-CSRF-Token": csrf},
        json={"requirement_code": "residence_proof_5yr", "applicability": "applicable"}
    )
    client.post(
        "/api/service/nativity-certificate/toggle",
        headers={"X-CSRF-Token": csrf},
        json={
            "requirement_code": "residence_proof_5yr",
            "is_completed": True,
            "selected_alternative": "School Education Certificate"
        }
    )

    # Mark all other requirements as not applicable
    for r in reqs:
        if r["requirement_code"] != "residence_proof_5yr":
            client.post(
                "/api/service/nativity-certificate/applicability",
                headers={"X-CSRF-Token": csrf},
                json={"requirement_code": r["requirement_code"], "applicability": "not_applicable"}
            )

    final_state = client.get("/api/service/nativity-certificate/state").get_json()
    assert final_state["progress"]["is_accepting"] is True
    assert final_state["progress"]["readiness_percentage"] == 100.0


def test_sink_state_absorbing_under_applicability(test_requirements):
    """Verifies that delta(q_sink, sigma) = q_sink under citizen applicability DFA."""
    dfa = ServiceDFA("srv_test", test_requirements, citizen_applicability={"doc_1": "applicable"})
    assert dfa.transition(SINK_STATE, "COMPLETE_doc_1") == SINK_STATE
    assert dfa.transition(SINK_STATE, "RESET") == SINK_STATE
    assert dfa.is_accepting(SINK_STATE) is False
    assert dfa.calculate_readiness(SINK_STATE) == 0.0


def test_order_independence_of_completion(test_requirements):
    """Verifies that completing documents in different orders reaches the exact same DFA state."""
    app_decisions = {r.key: "applicable" for r in test_requirements}
    dfa = ServiceDFA("srv_test", test_requirements, citizen_applicability=app_decisions)

    # Order 1: 1 -> 2 -> 3
    s1, _ = dfa.process_sequence(["COMPLETE_doc_1", "COMPLETE_doc_2", "COMPLETE_doc_3"])

    # Order 2: 3 -> 1 -> 2
    s2, _ = dfa.process_sequence(["COMPLETE_doc_3", "COMPLETE_doc_1", "COMPLETE_doc_2"])

    assert s1 == s2
    assert s1 == (1 << 0) | (1 << 1) | (1 << 2)
