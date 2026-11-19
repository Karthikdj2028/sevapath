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
    F: Set of accepting states (states where all applicable mandatory requirements are satisfied).
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
    Represents a single civic document requirement.
    
    Attributes:
        key (str): Unique requirement code (e.g. 'applicant_photo').
        name_en (str): English title.
        name_ta (str): Tamil title.
        is_mandatory (bool): True if mandatory, False if optional.
        is_conditional (bool): True if applicable only under specific conditions.
        condition_key (Optional[str]): Condition key (e.g. 'is_salaried').
        is_applicable (bool): Runtime applicability flag based on citizen context.
        description (str): Description of the document.
        help_text (str): Upload guidance / tips.
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
        help_text: str = ""
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
        }


class ServiceDFA:
    """
    Mathematically rigorous Deterministic Finite Automaton (DFA) for civic document readiness.
    
    Formal components:
        - Q: {0, 1, ..., 2^n - 1} U {SINK_STATE}
        - Sigma: {COMPLETE_r_i, UNCOMPLETE_r_i} U {RESET}
        - delta: Q x Sigma -> Q
        - q_0: 0
        - F: {q in Q | (q & mandatory_mask) == mandatory_mask and q != SINK_STATE}
    """

    COMPLETE_PREFIX = "COMPLETE_"
    UNCOMPLETE_PREFIX = "UNCOMPLETE_"
    RESET_SYMBOL = "RESET"

    def __init__(
        self,
        service_id: str,
        requirements: List[Requirement],
        active_conditions: Optional[Dict[str, bool]] = None
    ):
        self.service_id = service_id
        self.all_requirements = requirements
        self.active_conditions = active_conditions or {}

        # Filter applicable requirements based on active conditions
        self.applicable_requirements: List[Requirement] = []
        for req in requirements:
            if req.is_conditional and req.condition_key:
                # If condition key is present in active_conditions, evaluate; default False
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

        # Compute mandatory bitmask:
        # Bit i is 1 if and only if applicable_requirements[i] is mandatory
        self.mandatory_mask: int = 0
        self.mandatory_keys: Set[str] = set()
        self.optional_keys: Set[str] = set()

        for idx, req in enumerate(self.applicable_requirements):
            if req.is_mandatory:
                self.mandatory_mask |= (1 << idx)
                self.mandatory_keys.add(req.key)
            else:
                self.optional_keys.add(req.key)

        # Accepting states F:
        # Any state q in Q (excluding SINK_STATE) where all applicable mandatory bits are 1
        # When mandatory_mask is 0 (no mandatory requirements), q_0 is accepting.
        self.F: Set[int] = {
            q for q in self.Q 
            if q != SINK_STATE and (q & self.mandatory_mask) == self.mandatory_mask
        }

    def transition(self, current_state: int, symbol: str, strict: bool = False) -> int:
        """
        DFA Total Transition Function: delta(q, sigma) -> q'
        
        Properties:
        1. Absorbing sink: delta(q_sink, sigma) = q_sink for every sigma.
        2. Deterministic: identical (q, sigma) always yields the identical next state.
        3. Idempotent: repeated completions do not inflate state (q | bit == q).
        4. Rejection: unrecognized symbols transition to q_sink (or raise InvalidAlphabetSymbolError if strict).
        
        Args:
            current_state (int): Current state q in Q.
            symbol (str): Input symbol sigma in Sigma.
            strict (bool): If True, raises exception on invalid input instead of returning SINK_STATE.
            
        Returns:
            int: Next state q' in Q.
        """
        # Validate current state is in Q
        if current_state not in self.Q:
            if strict:
                raise InvalidStateError(f"State {current_state} is not in valid state space Q.")
            return SINK_STATE

        # 1. Absorbing sink state condition: delta(SINK_STATE, sigma) = SINK_STATE
        if current_state == SINK_STATE:
            return SINK_STATE

        # 2. Reset symbol: delta(q, RESET) = q_0
        if symbol == self.RESET_SYMBOL:
            return self.q_0

        # Validate symbol is in alphabet Sigma
        if symbol not in self.Sigma:
            if strict:
                raise InvalidAlphabetSymbolError(f"Symbol '{symbol}' is not in alphabet Sigma.")
            return SINK_STATE

        # 3. Document completion transition: delta(q, COMPLETE_r_i) = q | (1 << i)
        if symbol.startswith(self.COMPLETE_PREFIX):
            key = symbol[len(self.COMPLETE_PREFIX):]
            if key not in self.key_to_index:
                return SINK_STATE
            bit_idx = self.key_to_index[key]
            return current_state | (1 << bit_idx)

        # 4. Document uncomplete transition: delta(q, UNCOMPLETE_r_i) = q & ~(1 << i)
        elif symbol.startswith(self.UNCOMPLETE_PREFIX):
            key = symbol[len(self.UNCOMPLETE_PREFIX):]
            if key not in self.key_to_index:
                return SINK_STATE
            bit_idx = self.key_to_index[key]
            return current_state & ~(1 << bit_idx)

        if strict:
            raise InvalidAlphabetSymbolError(f"Unhandled symbol '{symbol}'.")
        return SINK_STATE

    def process_sequence(self, symbols: List[str], start_state: Optional[int] = None) -> Tuple[int, bool]:
        """
        Processes a sequence of input symbols w = sigma_1 sigma_2 ... sigma_k.
        
        Demonstrates order-independence:
        Permutations of completion symbols reach the exact same state q.
        """
        state = self.q_0 if start_state is None else start_state
        for symbol in symbols:
            state = self.transition(state, symbol, strict=False)
        return state, self.is_accepting(state)

    def is_accepting(self, state: int) -> bool:
        """Returns True if state q is in F (all mandatory requirements satisfied)."""
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

    def calculate_readiness(self, state: int) -> float:
        """
        Calculates readiness percentage based strictly on completed applicable mandatory requirements:
            Readiness % = (completed mandatory / total applicable mandatory) * 100
        
        Optional requirements do NOT count toward this percentage.
        Zero mandatory requirements case returns 100.0%.
        Sink state returns 0.0%.
        """
        if state == SINK_STATE:
            return 0.0

        if not self.mandatory_keys:
            return 100.0

        completed_keys = self.state_to_requirements(state)
        completed_mandatory = completed_keys.intersection(self.mandatory_keys)
        readiness = (len(completed_mandatory) / len(self.mandatory_keys)) * 100.0
        return round(readiness, 1)

    def get_progress_summary(self, state: int) -> Dict[str, Any]:
        """
        Generates a comprehensive progress report for the given state q.
        """
        completed_keys = self.state_to_requirements(state)
        completed_docs = []
        remaining_docs = []

        for req in self.applicable_requirements:
            req_info = req.to_dict()
            if req.key in completed_keys:
                req_info["completed"] = True
                completed_docs.append(req_info)
            else:
                req_info["completed"] = False
                remaining_docs.append(req_info)

        return {
            "service_id": self.service_id,
            "current_state": state,
            "state_label": f"q_{state}" if state != SINK_STATE else "q_sink (Error)",
            "is_initial": state == self.q_0,
            "is_accepting": self.is_accepting(state),
            "is_sink": self.is_sink(state),
            "readiness_percentage": self.calculate_readiness(state),
            "total_applicable_requirements": self.n,
            "total_mandatory_requirements": len(self.mandatory_keys),
            "total_optional_requirements": len(self.optional_keys),
            "completed_count": len(completed_docs),
            "remaining_count": len(remaining_docs),
            "completed_documents": completed_docs,
            "remaining_documents": remaining_docs,
        }

    def get_visualization_graph(self, current_state: int) -> Dict[str, Any]:
        """
        Generates nodes and edges for the frontend DFA visualization.
        
        Requirement 4 constraint:
        - If n <= 3: Generates the full state hypercube graph (all 2^n states).
          is_simplified_view = False.
        - If n > 3: Generates a neighborhood subgraph (q_0, current_state, immediate
          transitions, and target accepting state).
          is_simplified_view = True (explicitly labeled).
        """
        nodes = []
        edges = []
        is_simplified = self.n > 3

        if not is_simplified:
            # Complete state space for small n
            states_to_include = list(range(self.num_standard_states))
        else:
            # Simplified neighborhood view
            included_set = {self.q_0, self.mandatory_mask}
            if current_state != SINK_STATE:
                included_set.add(current_state)
                # 1-step forward transitions
                for idx in range(self.n):
                    forward = current_state | (1 << idx)
                    backward = current_state & ~(1 << idx)
                    included_set.add(forward)
                    included_set.add(backward)
            states_to_include = sorted(list(included_set))

        state_set = set(states_to_include)

        # Include sink state if current state is sink
        if current_state == SINK_STATE:
            states_to_include.append(SINK_STATE)
            state_set.add(SINK_STATE)

        for s in states_to_include:
            if s == SINK_STATE:
                nodes.append({
                    "id": s,
                    "label": "q_sink",
                    "bits": "N/A",
                    "is_accepting": False,
                    "is_current": True,
                    "is_initial": False,
                    "is_sink": True,
                    "readiness": 0.0,
                    "satisfied_keys": [],
                })
                continue

            satisfied = self.state_to_requirements(s)
            nodes.append({
                "id": s,
                "label": f"q_{s}" if s != self.q_0 else "q_0 (Start)",
                "bits": bin(s)[2:].zfill(self.n) if self.n > 0 else "0",
                "satisfied_count": len(satisfied),
                "is_accepting": self.is_accepting(s),
                "is_current": (s == current_state),
                "is_initial": (s == self.q_0),
                "is_sink": False,
                "readiness": self.calculate_readiness(s),
                "satisfied_keys": sorted(list(satisfied)),
            })

        # Generate transition edges between included states
        for s in states_to_include:
            if s == SINK_STATE:
                # Absorbing self-loop on sink
                edges.append({
                    "from": SINK_STATE,
                    "to": SINK_STATE,
                    "symbol": "any",
                    "label": "any (absorbing)",
                    "is_active_transition": current_state == SINK_STATE,
                })
                continue

            for idx, req in enumerate(self.applicable_requirements):
                target = s | (1 << idx)
                if (s & (1 << idx)) == 0 and target in state_set:
                    is_active = (s == current_state and target == current_state | (1 << idx))
                    edges.append({
                        "from": s,
                        "to": target,
                        "symbol": f"COMPLETE_{req.key}",
                        "label": req.key,
                        "is_mandatory": req.is_mandatory,
                        "is_active_transition": is_active,
                    })

        return {
            "service_id": self.service_id,
            "total_states": self.num_standard_states,
            "alphabet_size": len(self.Sigma),
            "current_state": current_state,
            "is_accepting": self.is_accepting(current_state),
            "is_sink": self.is_sink(current_state),
            "is_simplified_view": is_simplified,
            "view_description": (
                "Simplified Neighborhood View (Showing active, neighboring, and target states)" 
                if is_simplified else "Complete Finite State Automaton Graph"
            ),
            "readiness_percentage": self.calculate_readiness(current_state),
            "nodes": nodes,
            "edges": edges,
        }
