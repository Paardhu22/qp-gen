"""
AOS Core — Validation Framework
===================================
Reusable validation engine with modular rule composition.
Depends only on core.enums and core.datatypes.
"""

from typing import List, Dict, Any

from q_instructions.core.enums import (
    AcademicClass, BloomsLevel, StreamType, ValidationSeverity
)
from q_instructions.core.datatypes import (
    ExamBlueprint, ValidationError, ValidationReport
)
from q_instructions.core.interfaces import IValidationRule


# ---------------------------------------------------------------------------
# Built-in Validation Rules
# ---------------------------------------------------------------------------

class MarksSumRule(IValidationRule):
    """Validates that section marks sum to the declared total."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        calculated = sum(s.get_total_marks() for s in blueprint.sections)
        if calculated != blueprint.total_marks:
            errors.append(ValidationError(
                rule_name="MarksSumRule",
                severity=ValidationSeverity.ERROR,
                affected_element="Sections Configuration",
                error_message=f"Sum of section marks ({calculated}) != total ({blueprint.total_marks}).",
                suggested_remediation=f"Adjust sections to equal exactly {blueprint.total_marks}."
            ))
        return errors


class SectionSequenceRule(IValidationRule):
    """Enforces ascending marks across sections."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        last_marks = 0
        for sec in blueprint.sections:
            if sec.marks_per_question < last_marks:
                errors.append(ValidationError(
                    rule_name="SectionSequenceRule",
                    severity=ValidationSeverity.WARNING,
                    affected_element=f"Section {sec.section_id}",
                    error_message=f"Section {sec.section_id} marks ({sec.marks_per_question}) < prior ({last_marks}).",
                    suggested_remediation="CBSE recommends ascending marks: 1 → 2 → 3 → 5."
                ))
            last_marks = sec.marks_per_question
        return errors


class StreamBalanceRule(IValidationRule):
    """Ensures stream percentage splits fall within acceptable thresholds."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        stream_marks = target_data.get("stream_marks")
        if not stream_marks:
            return errors

        total = sum(stream_marks.values())
        if total == 0:
            return errors

        if blueprint.academic_class in [AcademicClass.CLASS_6, AcademicClass.CLASS_7]:
            return errors

        targets = getattr(blueprint, "stream_distribution_target", None) or getattr(blueprint, "stream_distribution", {})
        for stream, target_ratio in targets.items():
            actual = stream_marks.get(stream, 0) / total
            if abs(actual - target_ratio) > 0.05:
                errors.append(ValidationError(
                    rule_name="StreamBalanceRule",
                    severity=ValidationSeverity.WARNING,
                    affected_element=f"Stream Balance - {stream.value}",
                    error_message=f"{stream.value}: actual {actual:.2%}, target {target_ratio:.2%}.",
                    suggested_remediation="Redistribute questions across sub-disciplines."
                ))
        return errors


class ClassMaturityRule(IValidationRule):
    """Enforces progression ceilings for junior classes."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        bloom_data = target_data.get("bloom_distribution")
        if not bloom_data:
            return errors

        restricted = {BloomsLevel.EVALUATE, BloomsLevel.CREATE}
        is_junior = blueprint.academic_class in [
            AcademicClass.CLASS_6, AcademicClass.CLASS_7, AcademicClass.CLASS_8
        ]

        if is_junior:
            for level in restricted:
                if bloom_data.get(level, 0.0) > 0.0:
                    errors.append(ValidationError(
                        rule_name="ClassMaturityRule",
                        severity=ValidationSeverity.ERROR,
                        affected_element=f"Cognitive Bloom - {level.name}",
                        error_message=f"{level.name} assigned in {blueprint.academic_class.value}.",
                        suggested_remediation="Redistribute to REMEMBER, UNDERSTAND, or APPLY."
                    ))
        return errors


class CompetencyRatioRule(IValidationRule):
    """Ensures competency-based questions meet minimum board thresholds."""

    def execute(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        comp_count = target_data.get("competency_question_count", 0)
        total_count = target_data.get("total_question_count", 1)
        min_ratio = target_data.get("competency_minimum_ratio", 0.50)

        actual_ratio = comp_count / max(total_count, 1)
        if actual_ratio < min_ratio:
            errors.append(ValidationError(
                rule_name="CompetencyRatioRule",
                severity=ValidationSeverity.ERROR,
                affected_element="Competency Distribution",
                error_message=f"Competency ratio {actual_ratio:.2%} < minimum {min_ratio:.2%}.",
                suggested_remediation="Increase competency-based question count."
            ))
        return errors


# ---------------------------------------------------------------------------
# Orchestrated Validator
# ---------------------------------------------------------------------------

class ValidationOrchestrator:
    """Aggregates and executes modular validation policies by category."""

    def __init__(self) -> None:
        self.structure_validators: List[IValidationRule] = [
            MarksSumRule(),
            SectionSequenceRule(),
        ]
        self.curriculum_validators: List[IValidationRule] = [
            StreamBalanceRule(),
            ClassMaturityRule(),
        ]
        self.board_validators: List[IValidationRule] = [
            CompetencyRatioRule(),
        ]
        self.psychometric_validators: List[IValidationRule] = []
        self.accessibility_validators: List[IValidationRule] = []
        self.hallucination_validators: List[IValidationRule] = []

    def validate(self, blueprint: ExamBlueprint, target_data: Dict[str, Any]) -> ValidationReport:
        """Executes all rules across all categories and compiles results."""
        report = ValidationReport(is_valid=True)
        all_errors: List[ValidationError] = []

        all_rules = (self.structure_validators + self.curriculum_validators + 
                     self.board_validators + self.psychometric_validators + 
                     self.accessibility_validators + self.hallucination_validators)

        for rule in all_rules:
            try:
                all_errors.extend(rule.execute(blueprint, target_data))
            except Exception as e:
                all_errors.append(ValidationError(
                    rule_name=rule.__class__.__name__,
                    severity=ValidationSeverity.ERROR,
                    affected_element="Validator Execution",
                    error_message=f"Validation crashed: {e}",
                    suggested_remediation="Review rule logic."
                ))

        report.errors = all_errors
        report.is_valid = not any(
            e.severity == ValidationSeverity.ERROR for e in all_errors
        )

        report.diagnostics["total_marks"] = blueprint.total_marks
        report.diagnostics["sections"] = [s.section_id for s in blueprint.sections]
        report.diagnostics["class"] = blueprint.academic_class.value
        report.diagnostics["rule_count"] = len(all_rules)

        return report
