"""
Question Generation Domain - Custom Exceptions
"""


class QGError(Exception):
    pass


class BlueprintCompilationError(QGError):
    pass


class ConceptNotFoundError(QGError):
    def __init__(self, concept_id: str) -> None:
        super().__init__(f"Concept '{concept_id}' not found in curriculum graph.")
        self.concept_id = concept_id


class CyclicDependencyError(QGError):
    def __init__(self, cycle_path: str) -> None:
        super().__init__(f"Cyclic dependency detected: {cycle_path}")
        self.cycle_path = cycle_path


class MarksValidationError(QGError):
    pass


class StreamBalanceError(QGError):
    pass


class HallucinationDetectedError(QGError):
    def __init__(self, term: str) -> None:
        super().__init__(f"Hallucinated term detected: '{term}'")
        self.term = term


class BoardPolicyViolationError(QGError):
    pass


class RetrievalEmptyError(QGError):
    def __init__(self, concept_id: str) -> None:
        super().__init__(f"No context retrieved for concept '{concept_id}'.")
        self.concept_id = concept_id


class SubjectNotRegisteredError(QGError):
    def __init__(self, subject_name: str) -> None:
        super().__init__(f"Subject '{subject_name}' is not registered.")
        self.subject_name = subject_name
