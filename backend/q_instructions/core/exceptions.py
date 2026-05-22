"""
AOS Core — Custom Exception Hierarchy
========================================
Structured exceptions for the Academic Operating System.
All modules raise these instead of generic Python exceptions.
"""


class AOSError(Exception):
    """Base exception for all AOS errors."""
    pass


class BlueprintCompilationError(AOSError):
    """Raised when blueprint compilation fails validation."""
    pass


class ConceptNotFoundError(AOSError):
    """Raised when a concept ID is not found in the curriculum graph."""
    def __init__(self, concept_id: str):
        super().__init__(f"Concept '{concept_id}' not found in curriculum graph.")
        self.concept_id = concept_id


class CyclicDependencyError(AOSError):
    """Raised when a circular prerequisite chain is detected."""
    def __init__(self, cycle_path: str):
        super().__init__(f"Cyclic dependency detected: {cycle_path}")
        self.cycle_path = cycle_path


class MarksValidationError(AOSError):
    """Raised when marks allocation violates board policies."""
    pass


class StreamBalanceError(AOSError):
    """Raised when stream distribution exceeds acceptable thresholds."""
    pass


class HallucinationDetectedError(AOSError):
    """Raised when generated content contains forbidden/hallucinated terminology."""
    def __init__(self, term: str):
        super().__init__(f"Hallucinated term detected: '{term}'")
        self.term = term


class BoardPolicyViolationError(AOSError):
    """Raised when a paper violates board-level compliance rules."""
    pass


class RetrievalEmptyError(AOSError):
    """Raised when semantic retrieval returns no matching context."""
    def __init__(self, concept_id: str):
        super().__init__(f"No context retrieved for concept '{concept_id}'.")
        self.concept_id = concept_id


class SubjectNotRegisteredError(AOSError):
    """Raised when requesting an unregistered subject plugin."""
    def __init__(self, subject_name: str):
        super().__init__(f"Subject '{subject_name}' is not registered.")
        self.subject_name = subject_name
