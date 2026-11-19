"""
Pytest unit tests for the SevaPath Deterministic Finite Automaton (DFA) Engine.

Mathematically verifies:
M = (Q, Sigma, delta, q_0, F)
- Absorbing sink state delta(q_sink, sigma) = q_sink
- Order independence of verification events
- Idempotency of completion transitions
- Mandatory vs. optional vs. conditional requirement handling
- Zero-requirement edge cases
- State decoding and readiness calculations
"""

import pytest
from app.core.dfa_engine import ServiceDFA, Requirement, SINK_STATE, InvalidAlphabetSymbolError


@pytest.fixture
def sample_requirements():
    """Provides standard test requirements: 2 mandatory, 1 optional, 1 conditional."""
    return [
        Requirement(key="r1_photo", name_en="Photo", name_ta="புகைப்படம்", is_mandatory=True),
        Requirement(key="r2_address", name_en="Address Proof", name_ta="முகவரி சான்று", is_mandatory=True),
        Requirement(key="r3_optional_tax", name_en="IT Return", name_ta="வருமான வரி", is_mandatory=False),
        Requirement(
            key="r4_salary_slip",
            name_en="Salary Slip",
            name_ta="சம்பள ரசீது",
            is_mandatory=True,
            is_conditional=True,
            condition_key="is_salaried"
        ),
    ]


def test_dfa_initialization(sample_requirements):
    """Verifies that DFA initializes with correct Q, Sigma, q_0 and mandatory mask."""
    # When condition 'is_salaried' is not set, r4_salary_slip is not applicable -> 3 applicable reqs
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    assert dfa.n == 3
    assert dfa.q_0 == 0
    # Q has 2^3 = 8 standard states + SINK_STATE (-1)
    assert len(dfa.Q) == 9
    assert SINK_STATE in dfa.Q
    assert "COMPLETE_r1_photo" in dfa.Sigma
    assert "UNCOMPLETE_r1_photo" in dfa.Sigma
    assert "RESET" in dfa.Sigma


def test_initial_state_non_accepting(sample_requirements):
    """Verifies initial state q_0 is non-accepting when mandatory requirements exist."""
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    assert not dfa.is_accepting(dfa.q_0)
    assert dfa.calculate_readiness(dfa.q_0) == 0.0


def test_single_completion_transition(sample_requirements):
    """Verifies delta(q_0, COMPLETE_r1) transitions to state with bit 0 set."""
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    next_state = dfa.transition(dfa.q_0, "COMPLETE_r1_photo")
    assert next_state == 1  # 1 << 0
    assert dfa.calculate_readiness(next_state) == 50.0  # 1 of 2 mandatory completed
    assert not dfa.is_accepting(next_state)


def test_order_independence(sample_requirements):
    """
    CRITICAL ACADEMIC REQUIREMENT:
    Demonstrates that completing documents in different orders yields identical final states.
    delta(delta(q_0, A), B) == delta(delta(q_0, B), A)
    """
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    
    # Path 1: r1 then r2
    state_seq_1, is_acc_1 = dfa.process_sequence(["COMPLETE_r1_photo", "COMPLETE_r2_address"])
    
    # Path 2: r2 then r1
    state_seq_2, is_acc_2 = dfa.process_sequence(["COMPLETE_r2_address", "COMPLETE_r1_photo"])
    
    assert state_seq_1 == state_seq_2
    assert is_acc_1 is True
    assert is_acc_2 is True
    assert dfa.calculate_readiness(state_seq_1) == 100.0


def test_accepting_state_reached_only_when_all_mandatory_complete(sample_requirements):
    """Verifies acceptance requires all applicable mandatory documents."""
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    
    # Complete only mandatory 1 -> not accepting
    s1 = dfa.transition(dfa.q_0, "COMPLETE_r1_photo")
    assert not dfa.is_accepting(s1)
    
    # Complete optional r3 -> not accepting
    s2 = dfa.transition(s1, "COMPLETE_r3_optional_tax")
    assert not dfa.is_accepting(s2)
    assert dfa.calculate_readiness(s2) == 50.0
    
    # Complete mandatory 2 -> now accepting!
    s3 = dfa.transition(s2, "COMPLETE_r2_address")
    assert dfa.is_accepting(s3)
    assert dfa.calculate_readiness(s3) == 100.0


def test_idempotent_completion(sample_requirements):
    """Verifies that repeating a completion event does not inflate state or readiness."""
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    s1 = dfa.transition(dfa.q_0, "COMPLETE_r1_photo")
    s2 = dfa.transition(s1, "COMPLETE_r1_photo")
    s3 = dfa.transition(s2, "COMPLETE_r1_photo")
    
    assert s1 == s2 == s3 == 1
    assert dfa.calculate_readiness(s3) == 50.0


def test_absorbing_sink_state(sample_requirements):
    """
    EXPLICIT REQUIREMENT 1:
    delta(q_sink, sigma) = q_sink for every input symbol.
    """
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    
    # Transition on invalid symbol yields SINK_STATE
    sink = dfa.transition(dfa.q_0, "INVALID_SYMBOL_XYZ")
    assert sink == SINK_STATE
    assert dfa.is_sink(sink)
    assert not dfa.is_accepting(sink)
    
    # Absorbing test: any valid or invalid input on SINK_STATE remains SINK_STATE
    assert dfa.transition(SINK_STATE, "COMPLETE_r1_photo") == SINK_STATE
    assert dfa.transition(SINK_STATE, "RESET") == SINK_STATE
    assert dfa.transition(SINK_STATE, "UNKNOWN_EVENT") == SINK_STATE


def test_strict_mode_exception(sample_requirements):
    """Verifies strict mode raises InvalidAlphabetSymbolError."""
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    with pytest.raises(InvalidAlphabetSymbolError):
        dfa.transition(dfa.q_0, "NON_EXISTENT_SYMBOL", strict=True)


def test_reset_functionality(sample_requirements):
    """Verifies delta(q, RESET) returns state to q_0 = 0."""
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    s = dfa.transition(dfa.q_0, "COMPLETE_r1_photo")
    s = dfa.transition(s, "COMPLETE_r2_address")
    assert s != dfa.q_0
    
    reset_state = dfa.transition(s, "RESET")
    assert reset_state == dfa.q_0 == 0
    assert dfa.calculate_readiness(reset_state) == 0.0


def test_optional_requirements_do_not_inflate_mandatory_readiness(sample_requirements):
    """Verifies that completing optional documents does not count toward mandatory readiness %."""
    dfa = ServiceDFA(service_id="test_srv", requirements=sample_requirements)
    
    # Complete optional r3 only
    s_opt = dfa.transition(dfa.q_0, "COMPLETE_r3_optional_tax")
    assert dfa.calculate_readiness(s_opt) == 0.0
    assert not dfa.is_accepting(s_opt)
    
    # Complete 1 mandatory + optional
    s_m1_opt = dfa.transition(s_opt, "COMPLETE_r1_photo")
    assert dfa.calculate_readiness(s_m1_opt) == 50.0
    assert not dfa.is_accepting(s_m1_opt)


def test_conditional_requirements_handling(sample_requirements):
    """
    EXPLICIT REQUIREMENT 3:
    Verifies that when conditions match, conditional requirements become active and mandatory.
    """
    # Context 1: is_salaried is True -> r4_salary_slip becomes active mandatory (total 3 mandatory)
    dfa_salaried = ServiceDFA(
        service_id="test_srv",
        requirements=sample_requirements,
        active_conditions={"is_salaried": True}
    )
    assert dfa_salaried.n == 4
    assert len(dfa_salaried.mandatory_keys) == 3
    assert "r4_salary_slip" in dfa_salaried.mandatory_keys
    
    # Completing r1 + r2 is NOT accepting yet (needs r4)
    s12 = dfa_salaried.transition(dfa_salaried.q_0, "COMPLETE_r1_photo")
    s12 = dfa_salaried.transition(s12, "COMPLETE_r2_address")
    assert not dfa_salaried.is_accepting(s12)
    assert dfa_salaried.calculate_readiness(s12) == round((2 / 3) * 100, 1)
    
    # Completing r4 reaches acceptance
    s124 = dfa_salaried.transition(s12, "COMPLETE_r4_salary_slip")
    assert dfa_salaried.is_accepting(s124)
    assert dfa_salaried.calculate_readiness(s124) == 100.0


def test_zero_applicable_mandatory_requirements():
    """Edge case: service with zero mandatory requirements is accepted at q_0 with 100% readiness."""
    optional_only = [
        Requirement(key="opt1", name_en="Optional Brochure", name_ta="துண்டுப்பிரசுரம்", is_mandatory=False)
    ]
    dfa = ServiceDFA(service_id="zero_srv", requirements=optional_only)
    assert dfa.is_accepting(dfa.q_0)
    assert dfa.calculate_readiness(dfa.q_0) == 100.0


def test_visualization_graph_metadata(sample_requirements):
    """Verifies that visualization graph labels simplified vs complete view accurately."""
    # When n <= 3: complete view
    dfa3 = ServiceDFA(service_id="s3", requirements=sample_requirements[:3])
    graph3 = dfa3.get_visualization_graph(current_state=0)
    assert graph3["is_simplified_view"] is False
    assert len(graph3["nodes"]) == 8  # 2^3
    
    # When n > 3: simplified view
    dfa4 = ServiceDFA(service_id="s4", requirements=sample_requirements, active_conditions={"is_salaried": True})
    graph4 = dfa4.get_visualization_graph(current_state=0)
    assert graph4["is_simplified_view"] is True
    assert "Simplified" in graph4["view_description"]
