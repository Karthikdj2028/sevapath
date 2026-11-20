r"""
SevaPath - Deterministic Finite Automaton (DFA) Preparation Engine.

Academic Definition:
A Deterministic Finite Automaton (DFA) M is formally defined as a 5-tuple:
    M = (Q, Sigma, delta, q_0, F)

Where:
    Q: Finite set of states: {0, 1, ..., 2^n - 1} U {q_sink}, where non-sink
       states are represented as bitmasks of satisfied requirements.
       q_sink (-1) is the absorbing dead/rejection state for invalid inputs.
    Sigma: Finite set of input symbols (the alphabet):
           {COMPLETE_r_i, UNCOMPLETE_r_i | r_i in R} U {RESET}
    delta: Total transition function Q x Sigma -> Q.
           - delta(q_sink, sigma) = q_sink for all sigma in Sigma (absorbing).
           - For q in Q \ {q_sink} and COMPLETE_r_i: delta(q, COMPLETE_r_i) = q | (1 << i)
           - For q in Q \ {q_sink} and UNCOMPLETE_r_i: delta(q, UNCOMPLETE_r_i) = q & ~(1 << i)
           - For q in Q \ {q_sink} and RESET: delta(q, RESET) = q_0
           - For invalid/unrecognized inputs: delta(q, invalid) = q_sink
    q_0: The initial state, represented as bitmask 0 (no documents verified).
    F: Set of accepting states (states where all applicable mandatory or citizen-selected requirements are satisfied).

Phase 4 Citizen Preparation & Applicability Model:
Distinguishes:
1. Official classification: What TNeGA/e-Sevai officially lists.
2. Citizen-specific applicability: 'applicable', 'not_applicable', 'undetermined'.
3. DFA completion target M_session: Target bitmask dynamically built over citizen-selected applicable requirements.
4. Empty-checklist protection: An empty or undetermined checklist never yields 100% readiness or acceptance.
"""

from typing import List, Dict, Set, Optional, Tuple, Any

# Constant for absorbing sink/dead state
SINK_STATE = -1


class DFAError(Exception):
    """Base exception for DFA operations."""
    pass


class InvalidAlphabetSymbolError(DFAError):
    """Raised when an input symbol is not in Sigma in strict mode."""
    pass


class InvalidStateError(DFAError):
    """Raised when encountering an invalid state outside Q."""
    pass


class Requirement:
    """
    Represents a single civic document requirement with official classification and citizen applicability.
    """

    def __init__(
        self,
        key: str,
        name_en: str,
        name_ta: str,
        is_mandatory: bool = True,
        is_conditional: bool = False,
        condition_key: Optional[str] = None,
        is_applicable: bool = True,
        description: str = "",
        help_text: str = "",
        presentation_category: str = "listed_applicability_unconfirmed",
        logical_group: Optional[str] = None,
        alternatives: Optional[List[Dict[str, str]]] = None,
        applicability: str = "undetermined",
        selected_alternative: Optional[str] = None
    ):
        self.key = key
        self.name_en = name_en
        self.name_ta = name_ta
        self.is_mandatory = is_mandatory
        self.is_conditional = is_conditional
        self.condition_key = condition_key
        self.is_applicable = is_applicable
        self.description = description
        self.help_text = help_text
        self.presentation_category = presentation_category
        self.logical_group = logical_group
        self.alternatives = alternatives or []
        self.applicability = applicability
        self.selected_alternative = selected_alternative

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name_en": self.name_en,
            "name_ta": self.name_ta,
            "is_mandatory": self.is_mandatory,
            "is_conditional": self.is_conditional,
            "condition_key": self.condition_key,
            "is_applicable": self.is_applicable,
            "description": self.description,
            "help_text": self.help_text,
            "presentation_category": self.presentation_category,
            "logical_group": self.logical_group,
            "alternatives": self.alternatives,
            "applicability": self.applicability,
            "selected_alternative": self.selected_alternative,
        }


class ServiceDFA:
    """
    Mathematically rigorous Deterministic Finite Automaton (DFA) for civic document readiness.

    Supports:
    - Phase 2 static mandatory bitmask (backward-compatible fallback).
    - Phase 4 citizen-specific applicability target mask M_session.
    - Empty-checklist protection and multi-stage readiness semantics.
    """

    COMPLETE_PREFIX = "COMPLETE_"
    UNCOMPLETE_PREFIX = "UNCOMPLETE_"
    RESET_SYMBOL = "RESET"

    def __init__(
        self,
        service_id: str,
        requirements: List[Requirement],
        active_conditions: Optional[Dict[str, bool]] = None,
        citizen_applicability: Optional[Dict[str, str]] = None
    ):
        self.service_id = service_id
        self.all_requirements = requirements
        self.active_conditions = active_conditions or {}
        self.citizen_applicability = citizen_applicability

        # Filter applicable requirements based on active conditions
        self.applicable_requirements: List[Requirement] = []
        for req in requirements:
            if req.is_conditional and req.condition_key:
                req.is_applicable = bool(self.active_conditions.get(req.condition_key, False))
            else:
                req.is_applicable = True

            if req.is_applicable:
                self.applicable_requirements.append(req)

        self.n = len(self.applicable_requirements)

        # Mapping key <-> bit position (0 to n - 1)
        self.key_to_index: Dict[str, int] = {
            req.key: idx for idx, req in enumerate(self.applicable_requirements)
        }
        self.index_to_key: Dict[int, str] = {
            idx: req.key for idx, req in enumerate(self.applicable_requirements)
        }

        # Finite state space Q: 2^n standard states plus SINK_STATE (-1)
        self.num_standard_states = 1 << self.n
        self.Q: Set[int] = set(range(self.num_standard_states))
        self.Q.add(SINK_STATE)

        # Initial state q_0: bitmask 0
        self.q_0: int = 0

        # Input alphabet Sigma
        self.Sigma: Set[str] = {self.RESET_SYMBOL}
        for req in self.applicable_requirements:
            self.Sigma.add(f"{self.COMPLETE_PREFIX}{req.key}")
            self.Sigma.add(f"{self.UNCOMPLETE_PREFIX}{req.key}")

        # Citizen applicability resolution
        if self.citizen_applicability is not None:
            self.has_citizen_applicability = True
            self.applicable_keys: Set[str] = {
                k for k, v in self.citizen_applicability.items()
                if v == "applicable" and k in self.key_to_index
            }
            self.undetermined_keys: Set[str] = {
                k for k, v in self.citizen_applicability.items()
                if v == "undetermined" and k in self.key_to_index
            }
            self.not_applicable_keys: Set[str] = {
                k for k, v in self.citizen_applicability.items()
                if v == "not_applicable" and k in self.key_to_index
            }

            # Target mask M_session: bitwise OR of 2^i for each citizen-selected applicable item
            self.target_mask: int = 0
            for k in self.applicable_keys:
                self.target_mask |= (1 << self.key_to_index[k])

            self.mandatory_mask = self.target_mask
            self.mandatory_keys = self.applicable_keys
            self.optional_keys = self.not_applicable_keys.union(self.undetermined_keys)

            # Accepting states F:
            # Requires at least one applicable requirement, zero undetermined requirements,
            # and all applicable bits completed.
            if len(self.applicable_keys) > 0 and len(self.undetermined_keys) == 0:
                self.F: Set[int] = {
                    q for q in self.Q
                    if q != SINK_STATE and (q & self.target_mask) == self.target_mask
                }
            else:
                self.F = set()
        else:
            # Backward-compatibility fallback: use req.is_mandatory
            self.has_citizen_applicability = False
            self.applicable_keys = set()
            self.undetermined_keys = set()
            self.not_applicable_keys = set()
            self.mandatory_mask = 0
            self.mandatory_keys = set()
            self.optional_keys = set()

            for idx, req in enumerate(self.applicable_requirements):
                if req.is_mandatory:
                    self.mandatory_mask |= (1 << idx)
                    self.mandatory_keys.add(req.key)
                else:
                    self.optional_keys.add(req.key)

            self.target_mask = self.mandatory_mask
            self.F = {
                q for q in self.Q
                if q != SINK_STATE and (q & self.mandatory_mask) == self.mandatory_mask
            }

    def transition(self, current_state: int, symbol: str, strict: bool = False) -> int:
        """
        DFA Total Transition Function: delta(q, sigma) -> q'
        """
        if current_state not in self.Q:
            if strict:
                raise InvalidStateError(f"State {current_state} is not in Q.")
            return SINK_STATE

        # 1. Absorbing sink state: delta(q_sink, sigma) = q_sink for every sigma
        if current_state == SINK_STATE:
            return SINK_STATE

        # 2. Reset symbol: delta(q, RESET) = q_0
        if symbol == self.RESET_SYMBOL:
            return self.q_0

        # 3. Requirement completion: delta(q, COMPLETE_r_i) = q | (1 << i)
        if symbol.startswith(self.COMPLETE_PREFIX):
            key = symbol[len(self.COMPLETE_PREFIX):]
            if key in self.key_to_index:
                bit_pos = self.key_to_index[key]
                return current_state | (1 << bit_pos)

        # 4. Requirement revocation: delta(q, UNCOMPLETE_r_i) = q & ~(1 << i)
        if symbol.startswith(self.UNCOMPLETE_PREFIX):
            key = symbol[len(self.UNCOMPLETE_PREFIX):]
            if key in self.key_to_index:
                bit_pos = self.key_to_index[key]
                return current_state & ~(1 << bit_pos)

        # 5. Invalid / Unrecognized input
        if strict:
            raise InvalidAlphabetSymbolError(f"Symbol '{symbol}' is not in Sigma.")
        return SINK_STATE

    def process_sequence(self, symbols: List[str], start_state: Optional[int] = None) -> Tuple[int, bool]:
        """Processes a sequence of input symbols w = sigma_1 sigma_2 ... sigma_k."""
        state = self.q_0 if start_state is None else start_state
        for symbol in symbols:
            state = self.transition(state, symbol, strict=False)
        return state, self.is_accepting(state)

    def is_accepting(self, state: int) -> bool:
        """Returns True if state q is in F."""
        return state in self.F

    def is_sink(self, state: int) -> bool:
        """Returns True if state q is the absorbing dead/sink state."""
        return state == SINK_STATE

    def state_to_requirements(self, state: int) -> Set[str]:
        """Decodes state bitmask into a set of satisfied requirement keys."""
        if state == SINK_STATE or state not in self.Q:
            return set()
        satisfied = set()
        for idx in range(self.n):
            if (state & (1 << idx)) != 0:
                satisfied.add(self.index_to_key[idx])
        return satisfied

    def requirements_to_state(self, satisfied_keys: Set[str]) -> int:
        """Encodes a set of satisfied requirement keys into a valid state bitmask."""
        state = 0
        for key in satisfied_keys:
            if key in self.key_to_index:
                state |= (1 << self.key_to_index[key])
        return state

    def get_readiness_stage(self, state: int) -> str:
        """
        Determines the preparation readiness stage:
        1. 'not_started': No applicability decisions made yet.
        2. 'undetermined': Some applicability decisions remain undetermined.
        3. 'in_progress': All applicability decisions made, but applicable items are incomplete.
        4. 'complete': All applicability decisions made and all applicable items are prepared.
        """
        if state == SINK_STATE:
            return "error"

        if not self.has_citizen_applicability:
            if self.is_accepting(state):
                return "complete"
            return "in_progress" if state != self.q_0 else "not_started"

        total_reqs = self.n
        if total_reqs == 0:
            return "not_started"

        # Check applicability decisions
        if len(self.undetermined_keys) == total_reqs or (len(self.applicable_keys) == 0 and len(self.not_applicable_keys) == 0):
            return "not_started"

        if len(self.undetermined_keys) > 0:
            return "undetermined"

        if len(self.applicable_keys) == 0:
            # All marked not applicable (no applicable items to prepare)
            return "not_started"

        if self.is_accepting(state):
            return "complete"

        return "in_progress"

    def calculate_readiness(self, state: int) -> float:
        """
        Calculates preparation readiness percentage.
        Empty-checklist protection: Returns 0.0% if no requirements are marked applicable.
        """
        if state == SINK_STATE:
            return 0.0

        if self.has_citizen_applicability:
            # Empty checklist protection
            if not self.applicable_keys:
                return 0.0

            completed_keys = self.state_to_requirements(state)
            completed_applicable = completed_keys.intersection(self.applicable_keys)
            readiness = (len(completed_applicable) / len(self.applicable_keys)) * 100.0
            return round(readiness, 1)
        else:
            # Fallback legacy calculation
            if not self.mandatory_keys:
                return 100.0
            completed_keys = self.state_to_requirements(state)
            completed_mandatory = completed_keys.intersection(self.mandatory_keys)
            readiness = (len(completed_mandatory) / len(self.mandatory_keys)) * 100.0
            return round(readiness, 1)

    def get_progress_summary(self, state: int) -> Dict[str, Any]:
        """
        Generates a comprehensive progress report for state q.
        """
        completed_keys = self.state_to_requirements(state)
        completed_docs = []
        remaining_docs = []
        undetermined_docs = []
        not_applicable_docs = []

        for req in self.applicable_requirements:
            req_info = req.to_dict()
            is_comp = req.key in completed_keys
            req_info["completed"] = is_comp

            app_val = req.applicability if self.has_citizen_applicability else ("applicable" if req.is_mandatory else "optional")
            req_info["applicability"] = app_val

            if app_val == "undetermined":
                undetermined_docs.append(req_info)
            elif app_val == "not_applicable":
                not_applicable_docs.append(req_info)
            elif is_comp:
                completed_docs.append(req_info)
            else:
                remaining_docs.append(req_info)

        stage = self.get_readiness_stage(state)
        readiness_pct = self.calculate_readiness(state)

        return {
            "service_id": self.service_id,
            "current_state": state,
            "state_label": f"q_{state}" if state != SINK_STATE else "q_sink (Error)",
            "is_initial": state == self.q_0,
            "is_accepting": self.is_accepting(state),
            "is_sink": self.is_sink(state),
            "readiness_percentage": readiness_pct,
            "readiness_stage": stage,
            "total_applicable_requirements": len(self.applicable_keys) if self.has_citizen_applicability else self.n,
            "total_mandatory_requirements": len(self.applicable_keys) if self.has_citizen_applicability else len(self.mandatory_keys),
            "completed_count": len(completed_docs),
            "remaining_count": len(remaining_docs),
            "undetermined_count": len(undetermined_docs),
            "not_applicable_count": len(not_applicable_docs),
            "completed_documents": completed_docs,
            "remaining_documents": remaining_docs,
            "undetermined_documents": undetermined_docs,
            "not_applicable_documents": not_applicable_docs,
        }

    def get_visualization_graph(self, current_state: int) -> Dict[str, Any]:
        """
        Generates state graph for UI visualization:
        - When n <= 3: renders complete state space (is_simplified_view = False).
        - When n > 3: renders simplified neighbor graph (is_simplified_view = True).
        """
        nodes = []
        edges = []

        if current_state == SINK_STATE:
            nodes.append({
                "id": "q_sink",
                "label": "q_sink (Rejection)",
                "is_current": True,
                "is_accepting": False,
                "is_sink": True,
                "completed_count": 0
            })
            return {
                "nodes": nodes,
                "edges": edges,
                "is_simplified_view": True,
                "view_description": "Simplified sink state",
                "current_state_id": "q_sink"
            }

        if self.n <= 3:
            # Complete state space visualization for small DFA (<= 8 states)
            for state in range(self.num_standard_states):
                nodes.append({
                    "id": f"q_{state}",
                    "label": f"q_{state}",
                    "is_current": state == current_state,
                    "is_accepting": self.is_accepting(state),
                    "is_sink": False,
                    "completed_count": len(self.state_to_requirements(state))
                })
            for state in range(self.num_standard_states):
                for req in self.applicable_requirements:
                    nxt = self.transition(state, f"{self.COMPLETE_PREFIX}{req.key}")
                    if nxt != state and nxt != SINK_STATE:
                        edges.append({
                            "from": f"q_{state}",
                            "to": f"q_{nxt}",
                            "label": f"+ {req.name_en[:18]}",
                            "action": "complete",
                            "requirement_code": req.key
                        })
            return {
                "nodes": nodes,
                "edges": edges,
                "is_simplified_view": False,
                "view_description": "Complete state space",
                "current_state_id": f"q_{current_state}"
            }
        else:
            # Simplified neighbor graph centered on current_state
            # 1. Initial State q_0
            nodes.append({
                "id": f"q_{self.q_0}",
                "label": "q_0 (Initial)",
                "is_current": current_state == self.q_0,
                "is_accepting": self.is_accepting(self.q_0),
                "is_sink": False,
                "completed_count": 0
            })

            # 2. Current State (if not q_0)
            completed_keys = self.state_to_requirements(current_state)
            if current_state != self.q_0:
                nodes.append({
                    "id": f"q_{current_state}",
                    "label": f"q_{current_state} (Current)",
                    "is_current": True,
                    "is_accepting": self.is_accepting(current_state),
                    "is_sink": False,
                    "completed_count": len(completed_keys)
                })

            # 3. Target / Accepting State
            target_state = self.target_mask
            if target_state not in (self.q_0, current_state) and target_state in self.Q:
                nodes.append({
                    "id": f"q_{target_state}",
                    "label": f"q_{target_state} (Target Complete)",
                    "is_current": False,
                    "is_accepting": True,
                    "is_sink": False,
                    "completed_count": len(self.applicable_keys) if self.has_citizen_applicability else len(self.mandatory_keys)
                })

            # Generate neighbor transitions from current_state
            for req in self.applicable_requirements:
                key = req.key
                next_state = self.transition(current_state, f"{self.COMPLETE_PREFIX}{key}")
                if next_state != current_state and next_state != SINK_STATE:
                    node_id = f"q_{next_state}"
                    if not any(n["id"] == node_id for n in nodes):
                        nodes.append({
                            "id": node_id,
                            "label": f"q_{next_state}",
                            "is_current": False,
                            "is_accepting": self.is_accepting(next_state),
                            "is_sink": False,
                            "completed_count": len(self.state_to_requirements(next_state))
                        })
                    edges.append({
                        "from": f"q_{current_state}",
                        "to": node_id,
                        "label": f"+ {req.name_en[:18]}",
                        "action": "complete",
                        "requirement_code": key
                    })

            return {
                "nodes": nodes,
                "edges": edges,
                "is_simplified_view": True,
                "view_description": "Simplified neighbor transition graph",
                "current_state_id": f"q_{current_state}"
            }
