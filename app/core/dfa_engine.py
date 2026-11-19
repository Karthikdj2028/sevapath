"""
SevaPath - Deterministic Finite Automaton (DFA) Preparation Engine.

Academic Definition:
A Deterministic Finite Automaton (DFA) M is formally defined as a 5-tuple:
    M = (Q, Sigma, delta, q_0, F)

Where:
    Q: Finite set of states, represented as integers/bitmasks (0 <= state < 2^n),
       where each bit corresponds to a verified civic requirement.
    Sigma: Finite set of input symbols (the alphabet), representing completion
           events for specific documents (e.g., 'VERIFY_doc_photo').
    delta: Transition function Q x Sigma -> Q.
           Given a current state and an input symbol, delta returns the uniquely
           determined next state. Invalid symbols outside Sigma are rejected.
    q_0: The initial state, represented as bitmask 0 (no documents verified).
    F: Set of accepting states (states where all mandatory requirements are satisfied).
"""

from typing import List, Dict, Set, Optional, Tuple, Any


class DFAError(Exception):
    """Base exception for DFA operations."""
    pass


class InvalidAlphabetSymbolError(DFAError):
    """Raised when an input symbol is not in Sigma."""
    pass


class InvalidStateError(DFAError):
    """Raised when encountering a state not in Q."""
    pass


class Requirement:
    """Represents a single civic document requirement."""

    def __init__(self, key: str, name_en: str, name_ta: str, is_mandatory: bool = True, description: str = ""):
        self.key = key
        self.name_en = name_en
        self.name_ta = name_ta
        self.is_mandatory = is_mandatory
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name_en": self.name_en,
            "name_ta": self.name_ta,
            "is_mandatory": self.is_mandatory,
            "description": self.description,
        }


class ServiceDFA:
    """
    Genuine Deterministic Finite Automaton (DFA) implementation for service readiness.
    
    Attributes:
        service_id (str): Identifier of the civic service.
        requirements (List[Requirement]): Ordered list of requirements.
        n (int): Number of requirements (|R|).
        Q (Set[int]): Finite set of states {0, 1, ..., 2^n - 1}.
        Sigma (Set[str]): Input alphabet of verification events.
        q_0 (int): Initial state (0).
        F (Set[int]): Set of accepting states.
    """

    def __init__(self, service_id: str, requirements: List[Requirement]):
        self.service_id = service_id
        self.requirements = requirements
        self.n = len(requirements)

        # Map requirement key -> bit position (0 to n - 1)
        self.key_to_index: Dict[str, int] = {req.key: idx for idx, req in enumerate(requirements)}
        self.index_to_key: Dict[int, str] = {idx: req.key for idx, req in enumerate(requirements)}

        # State space Q: integers from 0 to 2^n - 1
        self.num_states = 1 << self.n
        self.Q: Set[int] = set(range(self.num_states))

        # Initial state q_0: bitmask 0
        self.q_0: int = 0

        # Input Alphabet Sigma:
        # For each requirement r_i:
        #   VERIFY_{r_i} -> marks requirement as completed
        #   REVOKE_{r_i} -> unmarks requirement (for interactive checklists)
        self.verify_prefix = "VERIFY_"
        self.revoke_prefix = "REVOKE_"
        self.Sigma: Set[str] = set()
        for req in requirements:
            self.Sigma.add(f"{self.verify_prefix}{req.key}")
            self.Sigma.add(f"{self.revoke_prefix}{req.key}")

        # Compute mandatory bitmask:
        # Bit i is 1 if and only if requirements[i] is mandatory.
        self.mandatory_mask: int = 0
        self.mandatory_keys: Set[str] = set()
        for idx, req in enumerate(requirements):
            if req.is_mandatory:
                self.mandatory_mask |= (1 << idx)
                self.mandatory_keys.add(req.key)

        # Set of accepting states F:
        # Any state q in Q where all mandatory bits are set ((q & mandatory_mask) == mandatory_mask)
        self.F: Set[int] = {
            q for q in self.Q if (q & self.mandatory_mask) == self.mandatory_mask
        }

    def transition(self, current_state: int, symbol: str) -> int:
        """
        DFA Transition Function: delta(q, sigma) -> q'
        
        Args:
            current_state (int): Current state q in Q.
            symbol (str): Input symbol sigma in Sigma.
            
        Returns:
            int: Next state q' in Q.
            
        Raises:
            InvalidStateError: If current_state is not in Q.
            InvalidAlphabetSymbolError: If symbol is not in Sigma.
        """
        if current_state not in self.Q:
            raise InvalidStateError(f"State {current_state} is not in valid state space Q (0..{self.num_states - 1}).")

        if symbol not in self.Sigma:
            raise InvalidAlphabetSymbolError(
                f"Input symbol '{symbol}' is not part of alphabet Sigma. "
                f"Allowed symbols: {sorted(list(self.Sigma))}"
            )

        if symbol.startswith(self.verify_prefix):
            key = symbol[len(self.verify_prefix):]
            bit_idx = self.key_to_index[key]
            # Bitwise OR transition: delta(q, VERIFY_k) = q | (1 << bit_idx)
            next_state = current_state | (1 << bit_idx)
            return next_state

        elif symbol.startswith(self.revoke_prefix):
            key = symbol[len(self.revoke_prefix):]
            bit_idx = self.key_to_index[key]
            # Bitwise AND with complement: delta(q, REVOKE_k) = q & ~(1 << bit_idx)
            next_state = current_state & ~(1 << bit_idx)
            return next_state

        raise InvalidAlphabetSymbolError(f"Symbol '{symbol}' cannot be evaluated.")

    def process_string(self, symbols: List[str], start_state: Optional[int] = None) -> Tuple[int, bool]:
        """
        Feeds an input string w = sigma_1 sigma_2 ... sigma_k into the DFA.
        
        Demonstrates order-independence:
        Given two permutations of the same verification symbols, both transition
        sequences reach the exact same state q_f.
        
        Returns:
            Tuple[int, bool]: (final_state, is_accepted)
        """
        state = self.q_0 if start_state is None else start_state
        for symbol in symbols:
            state = self.transition(state, symbol)
        return state, self.is_accepting(state)

    def is_accepting(self, state: int) -> bool:
        """Checks if state q in F (all mandatory requirements met)."""
        return state in self.F

    def state_to_requirements(self, state: int) -> Set[str]:
        """Decodes state bitmask into a set of satisfied requirement keys."""
        satisfied = set()
        for idx in range(self.n):
            if (state & (1 << idx)) != 0:
                satisfied.add(self.index_to_key[idx])
        return satisfied

    def requirements_to_state(self, satisfied_keys: Set[str]) -> int:
        """Encodes a set of satisfied requirement keys into a state bitmask."""
        state = 0
        for key in satisfied_keys:
            if key in self.key_to_index:
                state |= (1 << self.key_to_index[key])
        return state

    def get_missing_mandatory(self, state: int) -> List[Requirement]:
        """Returns list of mandatory requirements not yet satisfied in state q."""
        missing = []
        for idx, req in enumerate(self.requirements):
            if req.is_mandatory and (state & (1 << idx)) == 0:
                missing.append(req)
        return missing

    def get_completed(self, state: int) -> List[Requirement]:
        """Returns list of requirements satisfied in state q."""
        completed = []
        for idx, req in enumerate(self.requirements):
            if (state & (1 << idx)) != 0:
                completed.append(req)
        return completed

    def calculate_readiness(self, state: int) -> float:
        """
        Calculates readiness percentage based on satisfied mandatory requirements.
        Readiness = (Completed Mandatory / Total Mandatory) * 100.
        """
        if not self.mandatory_keys:
            return 100.0

        completed_keys = self.state_to_requirements(state)
        completed_mandatory = completed_keys.intersection(self.mandatory_keys)
        readiness = (len(completed_mandatory) / len(self.mandatory_keys)) * 100.0
        return round(readiness, 1)

    def get_visualization_graph(self, current_state: int) -> Dict[str, Any]:
        """
        Builds a graph representation of the DFA for UI visualization.
        
        To keep UI rendering clean and fast:
        - For n <= 4: Generates the full hypercube state graph.
        - For n > 4: Generates a contextual neighborhood subgraph (q_0, current_state,
          immediate neighbors, and the canonical all-mandatory accepting state).
        """
        nodes = []
        edges = []

        # Determine which states to render
        if self.n <= 4:
            states_to_include = list(range(self.num_states))
        else:
            # Contextual subgraph: initial, current, 1-step neighbors, accepting
            states_to_include_set = {self.q_0, current_state, self.mandatory_mask}
            # Add all 1-step forward transitions from current
            for idx in range(self.n):
                forward_state = current_state | (1 << idx)
                backward_state = current_state & ~(1 << idx)
                states_to_include_set.add(forward_state)
                states_to_include_set.add(backward_state)
            states_to_include = sorted(list(states_to_include_set))

        state_set = set(states_to_include)

        for s in states_to_include:
            satisfied = self.state_to_requirements(s)
            is_accept = self.is_accepting(s)
            is_current = (s == current_state)
            is_initial = (s == self.q_0)

            nodes.append({
                "id": s,
                "label": f"q_{s}" if not is_initial else "q_0 (Start)",
                "bits": bin(s)[2:].zfill(self.n),
                "satisfied_count": len(satisfied),
                "is_accepting": is_accept,
                "is_current": is_current,
                "is_initial": is_initial,
                "readiness": self.calculate_readiness(s),
                "satisfied_keys": sorted(list(satisfied)),
            })

        # Edges (transitions)
        for s in states_to_include:
            for idx, req in enumerate(self.requirements):
                target_state = s | (1 << idx)
                # Valid forward transition if bit was 0 and target is in included states
                if (s & (1 << idx)) == 0 and target_state in state_set:
                    is_active = (s == current_state and target_state == current_state | (1 << idx))
                    edges.append({
                        "from": s,
                        "to": target_state,
                        "symbol": f"VERIFY_{req.key}",
                        "label": req.key,
                        "is_active_transition": is_active,
                    })

        return {
            "service_id": self.service_id,
            "total_states": self.num_states,
            "alphabet_size": len(self.Sigma),
            "current_state": current_state,
            "is_accepting": self.is_accepting(current_state),
            "readiness_percentage": self.calculate_readiness(current_state),
            "nodes": nodes,
            "edges": edges,
        }
