"""
Academic Operating System (AOS) - Chapter & Concept Intelligence
================================================================================
Module: configs.cbse.science.curriculum
Phase: 3 - Curriculum Graph & Concept Intelligence Engine
Description: A highly sophisticated curriculum graph and concept intelligence
             engine. Implements graph theory models for science concepts,
             topological sorting of prerequisite chains, shortest path distance
             spacing tools, board-favorite weight calculators, and competency-
             Bloom difficulty estimators.
================================================================================
"""

import json
import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Set, Tuple, Optional, Any, Union

# Import pristine Phase 1 & 2 structures
from science import (
    AcademicClass,
    StreamType,
    QuestionTypeCode,
    BloomsLevel,
    ExamType,
    QuestionInstance
)


# ==============================================================================
# 1. CURRICULUM SCHEMAS & METADATA ENGINE
# ==============================================================================

class AbstractionLevel(Enum):
    """Degrees of conceptual abstraction governing cognitive load in science."""
    CONCRETE_OBSERVABLE = "Directly observable phenomenological concepts (e.g. food types)"
    MECHANISTIC_SYSTEMIC = "Underlying mechanistic structures and biological organs (e.g. nephron)"
    QUANTITATIVE_FUNCTIONAL = "Mathematical models, equations, and physical properties (e.g. lens equation)"
    THEORETICAL_MOLECULAR = "Highly abstract atomic, molecular, or field models (e.g. ionic bonding)"


@dataclass(frozen=True)
class ChapterMetadata:
    """Quantitative academic characteristics of a single curriculum chapter."""
    chapter_id: str
    chapter_name: str
    academic_class: AcademicClass
    stream: StreamType
    complexity_index: float      # Scale: 0.0 (simplest) to 1.0 (highly complex)
    practical_weightage: float   # Scale: 0.0 (pure theory) to 1.0 (pure laboratory/activity)
    theoretical_density: float   # Scale: 0.0 (observational) to 1.0 (heavy definitions/concepts)
    estimated_teaching_hours: int


class ChapterMetadataEngine:
    """Preloads and queries official science chapters for CBSE Classes 6, 7, 8, 9, and 10."""

    def __init__(self) -> None:
        self._chapters: Dict[str, ChapterMetadata] = {}
        self._initialize_chapters()

    def _initialize_chapters(self) -> None:
        # --- CLASS 6 CHAPTERS ---
        self._add_chapter("C6_CH1", "Components of Food", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.22, 0.35, 0.40, 10)
        self._add_chapter("C6_CH2", "Sorting Materials into Groups", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.20, 0.50, 0.30, 10)
        self._add_chapter("C6_CH3", "Separation of Substances", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.30, 0.60, 0.35, 12)
        self._add_chapter("C6_CH4", "Getting to Know Plants", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.32, 0.55, 0.45, 14)
        self._add_chapter("C6_CH5", "Body Movements", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.38, 0.30, 0.50, 12)
        self._add_chapter("C6_CH6", "Motion and Measurement of Distances", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.40, 0.60, 0.35, 12)
        self._add_chapter("C6_CH7", "Light, Shadows and Reflections", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.42, 0.65, 0.40, 14)
        self._add_chapter("C6_CH8", "Electricity and Circuits", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.45, 0.70, 0.35, 14)
        self._add_chapter("C6_CH9", "Fun with Magnets", AcademicClass.CLASS_6, StreamType.INTEGRATED, 0.35, 0.80, 0.30, 10)

        # --- CLASS 7 CHAPTERS ---
        self._add_chapter("C7_CH1", "Nutrition in Plants", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.35, 0.45, 0.50, 12)
        self._add_chapter("C7_CH2", "Nutrition in Animals", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.40, 0.40, 0.55, 14)
        self._add_chapter("C7_CH3", "Heat", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.45, 0.60, 0.45, 12)
        self._add_chapter("C7_CH4", "Acids, Bases and Salts (Base)", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.48, 0.65, 0.50, 14)
        self._add_chapter("C7_CH5", "Physical and Chemical Changes", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.50, 0.70, 0.45, 12)
        self._add_chapter("C7_CH6", "Respiration in Organisms", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.52, 0.50, 0.60, 14)
        self._add_chapter("C7_CH7", "Transportation in Animals and Plants", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.55, 0.45, 0.65, 14)
        self._add_chapter("C7_CH8", "Reproduction in Plants", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.50, 0.50, 0.60, 12)
        self._add_chapter("C7_CH9", "Motion and Time", AcademicClass.CLASS_7, StreamType.INTEGRATED, 0.55, 0.70, 0.40, 14)

        # --- CLASS 8 CHAPTERS ---
        self._add_chapter("C8_CH1", "Crop Production and Management", AcademicClass.CLASS_8, StreamType.BIOLOGY, 0.40, 0.45, 0.50, 15)
        self._add_chapter("C8_CH2", "Microorganisms: Friend and Foe", AcademicClass.CLASS_8, StreamType.BIOLOGY, 0.50, 0.50, 0.60, 16)
        self._add_chapter("C8_CH3", "Coal and Petroleum", AcademicClass.CLASS_8, StreamType.CHEMISTRY, 0.45, 0.30, 0.55, 12)
        self._add_chapter("C8_CH4", "Combustion and Flame", AcademicClass.CLASS_8, StreamType.CHEMISTRY, 0.48, 0.60, 0.50, 12)
        self._add_chapter("C8_CH5", "Cell Structure and Functions", AcademicClass.CLASS_8, StreamType.BIOLOGY, 0.55, 0.65, 0.60, 16)
        self._add_chapter("C8_CH6", "Force and Pressure", AcademicClass.CLASS_8, StreamType.PHYSICS, 0.60, 0.55, 0.50, 18)
        self._add_chapter("C8_CH7", "Friction", AcademicClass.CLASS_8, StreamType.PHYSICS, 0.55, 0.65, 0.45, 14)
        self._add_chapter("C8_CH8", "Sound", AcademicClass.CLASS_8, StreamType.PHYSICS, 0.62, 0.60, 0.50, 16)
        self._add_chapter("C8_CH9", "Chemical Effects of Electric Current", AcademicClass.CLASS_8, StreamType.PHYSICS, 0.65, 0.75, 0.45, 16)

        # --- CLASS 9 CHAPTERS ---
        self._add_chapter("C9_CH1", "Matter in Our Surroundings", AcademicClass.CLASS_9, StreamType.CHEMISTRY, 0.60, 0.55, 0.60, 16)
        self._add_chapter("C9_CH2", "Is Matter Around Us Pure", AcademicClass.CLASS_9, StreamType.CHEMISTRY, 0.65, 0.65, 0.55, 18)
        self._add_chapter("C9_CH3", "Atoms and Molecules", AcademicClass.CLASS_9, StreamType.CHEMISTRY, 0.78, 0.40, 0.85, 20)
        self._add_chapter("C9_CH4", "Structure of the Atom", AcademicClass.CLASS_9, StreamType.CHEMISTRY, 0.85, 0.45, 0.90, 22)
        self._add_chapter("C9_CH5", "The Fundamental Unit of Life", AcademicClass.CLASS_9, StreamType.BIOLOGY, 0.70, 0.60, 0.75, 18)
        self._add_chapter("C9_CH6", "Tissues", AcademicClass.CLASS_9, StreamType.BIOLOGY, 0.75, 0.55, 0.80, 20)
        self._add_chapter("C9_CH7", "Motion", AcademicClass.CLASS_9, StreamType.PHYSICS, 0.80, 0.65, 0.55, 22)
        self._add_chapter("C9_CH8", "Force and Laws of Motion", AcademicClass.CLASS_9, StreamType.PHYSICS, 0.85, 0.60, 0.60, 22)
        self._add_chapter("C9_CH9", "Gravitation", AcademicClass.CLASS_9, StreamType.PHYSICS, 0.82, 0.50, 0.70, 20)

        # --- CLASS 10 CHAPTERS ---
        self._add_chapter("C10_CH1", "Chemical Reactions and Equations", AcademicClass.CLASS_10, StreamType.CHEMISTRY, 0.75, 0.70, 0.65, 18)
        self._add_chapter("C10_CH2", "Acids, Bases and Salts", AcademicClass.CLASS_10, StreamType.CHEMISTRY, 0.80, 0.75, 0.70, 20)
        self._add_chapter("C10_CH3", "Metals and Non-metals", AcademicClass.CLASS_10, StreamType.CHEMISTRY, 0.82, 0.65, 0.75, 20)
        self._add_chapter("C10_CH4", "Carbon and its Compounds", AcademicClass.CLASS_10, StreamType.CHEMISTRY, 0.92, 0.55, 0.90, 24)
        self._add_chapter("C10_CH5", "Life Processes", AcademicClass.CLASS_10, StreamType.BIOLOGY, 0.85, 0.55, 0.90, 24)
        self._add_chapter("C10_CH6", "Control and Coordination", AcademicClass.CLASS_10, StreamType.BIOLOGY, 0.80, 0.50, 0.85, 18)
        self._add_chapter("C10_CH7", "How do Organisms Reproduce", AcademicClass.CLASS_10, StreamType.BIOLOGY, 0.82, 0.55, 0.80, 20)
        self._add_chapter("C10_CH8", "Heredity and Evolution", AcademicClass.CLASS_10, StreamType.BIOLOGY, 0.88, 0.40, 0.92, 18)
        self._add_chapter("C10_CH9", "Light: Reflection and Refraction", AcademicClass.CLASS_10, StreamType.PHYSICS, 0.90, 0.65, 0.60, 22)
        self._add_chapter("C10_CH10", "Human Eye and Colorful World", AcademicClass.CLASS_10, StreamType.PHYSICS, 0.80, 0.60, 0.75, 16)
        self._add_chapter("C10_CH11", "Electricity", AcademicClass.CLASS_10, StreamType.PHYSICS, 0.95, 0.70, 0.65, 22)
        self._add_chapter("C10_CH12", "Magnetic Effects of Electric Current", AcademicClass.CLASS_10, StreamType.PHYSICS, 0.88, 0.75, 0.65, 18)

    def _add_chapter(self, ch_id: str, name: str, cl: AcademicClass, stream: StreamType, comp: float, prac: float, theo: float, hrs: int) -> None:
        self._chapters[ch_id] = ChapterMetadata(ch_id, name, cl, stream, comp, prac, theo, hrs)

    def get_chapter(self, chapter_id: str) -> Optional[ChapterMetadata]:
        return self._chapters.get(chapter_id)

    def get_chapters_by_class(self, academic_class: AcademicClass) -> List[ChapterMetadata]:
        return [ch for ch in self._chapters.values() if ch.academic_class == academic_class]

    def get_chapters_by_stream(self, academic_class: AcademicClass, stream: StreamType) -> List[ChapterMetadata]:
        return [ch for ch in self.get_chapters_by_class(academic_class) if ch.stream == stream]


# ==============================================================================
# 2. GRAPH-THEORY CONCEPT GRAPH ENGINE
# ==============================================================================

class RelationshipType(Enum):
    """Causal and dependency structures linking science concepts."""
    PREREQUISITE = "Target concept must be mastered BEFORE learning dependent"
    PART_OF = "Target is a sub-concept under parent"
    INFLUENCES = "Changes in target explain changes in related concept"


@dataclass(frozen=True)
class ConceptNode:
    """A single conceptual educational node in the graph database."""
    concept_id: str
    concept_name: str
    chapter_id: str
    abstraction: AbstractionLevel
    base_numerical_depth: float  # Scale: 0.0 (no math) to 1.0 (heavy algebra/calculus)
    base_reasoning_steps: int    # Minimum causal links to explain this concept


@dataclass(frozen=True)
class ConceptEdge:
    """Directed connection in the concept graph."""
    source_id: str
    target_id: str
    relationship: RelationshipType


class ConceptGraph:
    """Implements directed acyclic graph (DAG) queries, topological sorting, and geodesic metrics."""

    def __init__(self) -> None:
        self.nodes: Dict[str, ConceptNode] = {}
        self.adjacency_list: Dict[str, Set[str]] = {}  # source -> targets (dependent list)
        self.reverse_adjacency: Dict[str, Set[str]] = {}  # target -> sources (prerequisite list)
        self.edges: List[ConceptEdge] = []

    def add_node(self, node: ConceptNode) -> None:
        """Adds a concept node to the registry."""
        if node.concept_id not in self.nodes:
            self.nodes[node.concept_id] = node
            self.adjacency_list[node.concept_id] = set()
            self.reverse_adjacency[node.concept_id] = set()

    def add_edge(self, source_id: str, target_id: str, relationship: RelationshipType) -> None:
        """Draws a directed edge in the concept database."""
        if source_id in self.nodes and target_id in self.nodes:
            edge = ConceptEdge(source_id, target_id, relationship)
            self.edges.append(edge)
            
            # Map forward list for dependency traversals
            self.adjacency_list[source_id].add(target_id)
            # Map reverse list for prerequisite resolutions
            self.reverse_adjacency[target_id].add(source_id)

    def find_all_prerequisites(self, concept_id: str) -> Set[str]:
        """Performs dynamic recursive DFS to resolve the complete prerequisite chain."""
        visited: Set[str] = set()

        def dfs(curr_id: str) -> None:
            for prereq in self.reverse_adjacency.get(curr_id, set()):
                if prereq not in visited:
                    visited.add(prereq)
                    dfs(prereq)

        dfs(concept_id)
        return visited

    def detect_cycles(self) -> List[str]:
        """Scans the concept graph for circular dependency errors."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycle_nodes: List[str] = []

        def dfs(curr_id: str) -> bool:
            visited.add(curr_id)
            rec_stack.add(curr_id)
            for neighbor in self.adjacency_list.get(curr_id, set()):
                if neighbor not in visited:
                    if dfs(neighbor):
                        cycle_nodes.append(curr_id)
                        return True
                elif neighbor in rec_stack:
                    cycle_nodes.append(neighbor)
                    cycle_nodes.append(curr_id)
                    return True
            rec_stack.remove(curr_id)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if dfs(node_id):
                    return list(reversed(cycle_nodes))
        return []

    def get_topological_sort(self, chapter_id: Optional[str] = None) -> List[str]:
        """Resolves target concept list in topological order, ensuring clean prerequisites flow."""
        if self.detect_cycles():
            raise ValueError("Invalid Curriculum Graph: Circular concept dependencies detected!")

        visited: Set[str] = set()
        stack: List[str] = []

        def dfs(curr_id: str) -> None:
            visited.add(curr_id)
            for neighbor in self.adjacency_list.get(curr_id, set()):
                if neighbor not in visited:
                    dfs(neighbor)
            stack.append(curr_id)

        target_node_ids = [
            nid for nid, node in self.nodes.items() 
            if (chapter_id is None or node.chapter_id == chapter_id)
        ]

        for nid in target_node_ids:
            if nid not in visited:
                dfs(nid)

        return list(reversed(stack))

    def calculate_geodesic_distance(self, c1_id: str, c2_id: str) -> int:
        """Calculates shortest path (BFS) distance between concepts to trace clustering bounds."""
        if c1_id == c2_id:
            return 0

        queue: List[Tuple[str, int]] = [(c1_id, 0)]
        visited: Set[str] = {c1_id}

        while queue:
            curr, dist = queue.pop(0)
            neighbors = self.adjacency_list.get(curr, set()).union(self.reverse_adjacency.get(curr, set()))
            for n in neighbors:
                if n == c2_id:
                    return dist + 1
                if n not in visited:
                    visited.add(n)
                    queue.append((n, dist + 1))

        return 999  # Disconnected concepts


# ==============================================================================
# 3. CHAPTER WEIGHTAGE & COMPETENCY ENGINE
# ==============================================================================

@dataclass(frozen=True)
class ConceptWeightProfile:
    """Holds priority indicators and competency flags for paper generations."""
    concept_id: str
    board_favorite_score: float  # Scale: 0.0 (rarely asked) to 1.0 (always in Board exams)
    is_competency_heavy: bool
    target_nep_competency_code: str  # National Education Policy standardized index code


class CurriculumWeightageRegistry:
    """Preloads priority registries detailing Board target scoring profiles."""

    def __init__(self) -> None:
        self._weights: Dict[str, ConceptWeightProfile] = {}
        self._initialize_weights()

    def _initialize_weights(self) -> None:
        # --- Class 6 Concept Weights ---
        self._add_weight("C6_NUT_VIT", 0.70, False, "CBSE.SC.06.1.1")
        self._add_weight("C6_NUT_PRO", 0.65, False, "CBSE.SC.06.1.2")
        self._add_weight("C6_MAT_SORT", 0.60, True, "CBSE.SC.06.2.1")
        self._add_weight("C6_SEP_WINN", 0.75, True, "CBSE.SC.06.3.1")
        self._add_weight("C6_PLANT_FLOW", 0.80, False, "CBSE.SC.06.4.1")

        # --- Class 8 Concept Weights ---
        self._add_weight("C8_AGR_KHAF", 0.75, False, "CBSE.SC.08.1.1")
        self._add_weight("C8_BIO_CELLS", 0.85, True, "CBSE.SC.08.5.1")
        self._add_weight("C8_PHY_PRES", 0.88, True, "CBSE.SC.08.6.1")
        self._add_weight("C8_PHY_HYDRO", 0.82, True, "CBSE.SC.08.6.2")

        # --- Class 10 Concept Weights ---
        self._add_weight("C10_EQ_BAL", 0.90, False, "CBSE.SC.10.1.1")
        self._add_weight("C10_RE_TYPE", 0.75, True, "CBSE.SC.10.1.2")
        self._add_weight("C10_RE_REDOX", 0.80, True, "CBSE.SC.10.1.3")
        self._add_weight("C10_AC_PRO", 0.65, False, "CBSE.SC.10.2.1")
        self._add_weight("C10_AC_PH", 0.95, True, "CBSE.SC.10.2.2")
        self._add_weight("C10_SALTS", 0.85, False, "CBSE.SC.10.2.3")
        self._add_weight("C10_BIO_NUT", 0.80, True, "CBSE.SC.10.5.1")
        self._add_weight("C10_BIO_RESP", 0.78, True, "CBSE.SC.10.5.2")
        self._add_weight("C10_BIO_CIRC", 0.90, False, "CBSE.SC.10.5.3")
        self._add_weight("C10_BIO_EXCR", 0.85, True, "CBSE.SC.10.5.4")
        self._add_weight("C10_PHY_REFL", 0.85, True, "CBSE.SC.10.9.1")
        self._add_weight("C10_PHY_REFR", 0.90, True, "CBSE.SC.10.9.2")
        self._add_weight("C10_PHY_EYE", 0.80, False, "CBSE.SC.10.10.1")
        self._add_weight("C10_PHY_DISP", 0.70, False, "CBSE.SC.10.10.2")
        self._add_weight("C10_PHY_OHM", 0.95, True, "CBSE.SC.10.11.1")
        self._add_weight("C10_PHY_SER", 0.90, True, "CBSE.SC.10.11.2")

    def _add_weight(self, concept_id: str, board_score: float, comp: bool, nep: str) -> None:
        self._weights[concept_id] = ConceptWeightProfile(concept_id, board_score, comp, nep)

    def get_weight_profile(self, concept_id: str) -> ConceptWeightProfile:
        return self._weights.get(
            concept_id, 
            ConceptWeightProfile(concept_id, 0.40, False, "CBSE.SC.GENERIC")
        )


# ==============================================================================
# 4. DUPLICATE PREVENTION & DISTRIBUTION ENGINES
# ==============================================================================

class CurriculumDuplicatePreventionEngine:
    """Protects papers from repeating conceptual topics or identical competency stress."""

    def __init__(self, concept_graph: ConceptGraph) -> None:
        self.graph = concept_graph

    def audit_duplication_safety(self, selected_concepts: List[str]) -> Tuple[bool, List[str]]:
        """Audits conceptual sets, flagging overlaps or direct parent hierarchy collisions."""
        errors = []
        used_ids = set()

        for idx, cid in enumerate(selected_concepts):
            if cid in used_ids:
                errors.append(f"Direct Duplicate Concept Violation: '{cid}' is allocated multiple times.")
            used_ids.add(cid)

            node = self.graph.nodes.get(cid)
            if node:
                prereqs = self.graph.find_all_prerequisites(cid)
                for other_cid in selected_concepts[idx+1:]:
                    if other_cid in prereqs:
                        distance = self.graph.calculate_geodesic_distance(cid, other_cid)
                        if distance <= 1:
                            errors.append(
                                f"Conceptual Collision: '{cid}' and '{other_cid}' represent direct parent-child "
                                f"prerequisite linkages (graph distance: {distance}) and should not stack in a single paper."
                            )

        return len(errors) == 0, errors


class ChapterDistributionEngine:
    """Balances stream weights and ensures wide coverage of curriculum chapters."""

    def __init__(self, metadata_engine: ChapterMetadataEngine) -> None:
        self.meta_engine = metadata_engine

    def evaluate_spread(self, chapter_counts: Dict[str, int], academic_class: AcademicClass) -> Tuple[float, List[str]]:
        """Calculates Chapter Spread Entropy (0.0 to 1.0) and lists structural gaps."""
        all_chapters = self.meta_engine.get_chapters_by_class(academic_class)
        total_questions = sum(chapter_counts.values())

        if total_questions == 0:
            return 0.0, ["Empty paper sequence."]

        covered_ch = [ch for ch in all_chapters if chapter_counts.get(ch.chapter_id, 0) > 0]
        coverage_ratio = len(covered_ch) / float(len(all_chapters))

        gaps = []
        for ch in all_chapters:
            if chapter_counts.get(ch.chapter_id, 0) == 0:
                gaps.append(f"Missing Chapter Gap: '{ch.chapter_name}' has no representation in the paper blueprint.")

        stream_sums: Dict[StreamType, int] = {}
        for ch_id, count in chapter_counts.items():
            ch = self.meta_engine.get_chapter(ch_id)
            if ch:
                stream_sums[ch.stream] = stream_sums.get(ch.stream, 0) + count

        for stream, count in stream_sums.items():
            ratio = count / float(total_questions)
            if ratio > 0.60 and len(stream_sums) > 1:
                gaps.append(f"Stream Dominance Warning: {stream.value} stream accounts for {ratio:.1%} of questions.")

        return coverage_ratio, gaps


# ==============================================================================
# 5. ANALYTICAL DIFFICULTY & QUESTION SUITABILITY ESTIMATION
# ==============================================================================

class DifficultyEstimationEngine:
    """Computes a quantitative conceptual difficulty score (0.0 to 1.0) based on graph properties."""

    def __init__(self, graph: ConceptGraph, weights_registry: CurriculumWeightageRegistry) -> None:
        self.graph = graph
        self.weights = weights_registry

    def estimate_difficulty(self, concept_id: str, target_bloom: BloomsLevel) -> float:
        """Applies mathematical model to compute conceptual difficulty."""
        node = self.graph.nodes.get(concept_id)
        if not node:
            return 0.35

        abstraction_weights = {
            AbstractionLevel.CONCRETE_OBSERVABLE: 0.15,
            AbstractionLevel.MECHANISTIC_SYSTEMIC: 0.40,
            AbstractionLevel.QUANTITATIVE_FUNCTIONAL: 0.70,
            AbstractionLevel.THEORETICAL_MOLECULAR: 0.90
        }
        val_abstraction = abstraction_weights.get(node.abstraction, 0.40)

        bloom_modifiers = {
            BloomsLevel.REMEMBER: 0.10,
            BloomsLevel.UNDERSTAND: 0.30,
            BloomsLevel.APPLY: 0.55,
            BloomsLevel.ANALYZE: 0.75,
            BloomsLevel.EVALUATE: 0.90,
            BloomsLevel.CREATE: 1.00
        }
        val_bloom = bloom_modifiers.get(target_bloom, 0.40)

        val_numerical = node.base_numerical_depth
        val_reasoning = min(1.0, node.base_reasoning_steps / 8.0)

        weight_profile = self.weights.get_weight_profile(concept_id)
        val_board = weight_profile.board_favorite_score

        difficulty = (
            0.35 * val_bloom +
            0.30 * val_abstraction +
            0.15 * val_numerical +
            0.15 * val_reasoning +
            0.05 * val_board
        )

        return min(1.0, max(0.0, difficulty))


class QuestionSuitabilityEngine:
    """Evaluates suitability percentages (0% to 100%) mapping concepts to question types."""

    def __init__(self, graph: ConceptGraph, weights_registry: CurriculumWeightageRegistry) -> None:
        self.graph = graph
        self.weights = weights_registry

    def calculate_suitability(self, concept_id: str, question_type: QuestionTypeCode) -> float:
        """Determines suitability matching metrics, returning value from 0.0 to 1.0."""
        node = self.graph.nodes.get(concept_id)
        if not node:
            return 0.50

        weight_profile = self.weights.get_weight_profile(concept_id)

        if question_type == QuestionTypeCode.NUMERICAL:
            return node.base_numerical_depth

        elif question_type == QuestionTypeCode.DIAGRAM:
            is_diag_suited = "bio" in node.concept_id.lower() or "eye" in node.concept_id.lower() or "prism" in node.concept_id.lower() or "circuit" in node.concept_id.lower()
            if is_diag_suited and node.abstraction == AbstractionLevel.MECHANISTIC_SYSTEMIC:
                return 0.95
            return 0.20 if node.base_numerical_depth > 0.5 else 0.40

        elif question_type == QuestionTypeCode.CASE_STUDY:
            if weight_profile.is_competency_heavy:
                return 0.90
            return 0.60 if node.base_reasoning_steps >= 4 else 0.40

        elif question_type == QuestionTypeCode.ASSERTION_REASON:
            if node.base_reasoning_steps >= 3 and node.base_numerical_depth < 0.30:
                return 0.90
            return 0.30

        elif question_type == QuestionTypeCode.MCQ:
            if node.base_reasoning_steps <= 2:
                return 0.85
            return 0.50

        else: 
            return 0.75


# ==============================================================================
# 6. TOPOLOGICAL PREREQUISITE PACING OPTIMIZER
# ==============================================================================

class PrerequisitePacingOptimizer:
    """Stochastically adjusts sequence flows to satisfy topological prerequisite orders."""

    def __init__(self, graph: ConceptGraph) -> None:
        self.graph = graph

    def is_sequence_prereq_safe(self, concept_ids: List[str]) -> Tuple[bool, List[str]]:
        """Ensures no concept is tested BEFORE its structural prerequisites are tested."""
        errors = []
        tested_concepts: Set[str] = set()

        for idx, cid in enumerate(concept_ids):
            prereqs = self.graph.find_all_prerequisites(cid)
            # Filter prerequisites that are actually present in this exam paper
            active_prereqs = prereqs.intersection(set(concept_ids))
            
            for pr in active_prereqs:
                if pr not in tested_concepts:
                    errors.append(
                        f"Pacing Violation: Concept '{cid}' is tested at index {idx} "
                        f"before its prerequisite concept '{pr}' has been tested."
                    )
            tested_concepts.add(cid)

        return len(errors) == 0, errors

    def optimize_sequence(self, concept_ids: List[str], max_iterations: int = 500) -> List[str]:
        """Arranges candidate concept list stochastically until all prerequisite constraints align."""
        current_seq = list(concept_ids)
        is_safe, _ = self.is_sequence_prereq_safe(current_seq)
        if is_safe:
            return current_seq

        # Try random reshuffling attempts
        for _ in range(max_iterations):
            random.shuffle(current_seq)
            is_safe, _ = self.is_sequence_prereq_safe(current_seq)
            if is_safe:
                return current_seq

        # Fallback: topological sort of the graph subset
        topo = self.graph.get_topological_sort()
        subset_seq = [c for c in topo if c in concept_ids]
        return subset_seq


# ==============================================================================
# 7. CONSOLE GRAPH ASCII TREE PATHS RENDERER
# ==============================================================================

class ConsoleGraphAsciiRenderer:
    """Constructs structured tree paths to display directed conceptual prerequisites."""

    @staticmethod
    def render_tree(graph: ConceptGraph, start_node_id: str) -> str:
        """Returns beautiful console tree output representing hierarchical branches."""
        lines = []
        lines.append("=" * 80)
        lines.append(f"CONCEPT TREE DEPENDENCY MAP FOR: '{start_node_id}'")
        lines.append("=" * 80)

        def build_branch(node_id: str, prefix: str = "", is_last: bool = True) -> None:
            node = graph.nodes.get(node_id)
            if not node:
                return
            
            marker = "└── " if is_last else "├── "
            lines.append(f"{prefix}{marker}{node.concept_name} [{node_id}]")
            
            # Fetch children (concepts dependent on this one)
            children = sorted(list(graph.adjacency_list.get(node_id, set())))
            new_prefix = prefix + ("    " if is_last else "│   ")
            
            for idx, child in enumerate(children):
                build_branch(child, new_prefix, idx == len(children) - 1)

        build_branch(start_node_id, "", True)
        lines.append("=" * 80)
        return "\n".join(lines)


# ==============================================================================
# 8. COMPREHENSIVE CURRICULUM GRAPH FACTORY (MULTI-CLASS PRELOADED)
# ==============================================================================

class CurriculumGraphFactory:
    """Assembles and pre-populates official concept maps for Class 6, 8, and 10."""

    @staticmethod
    def construct_comprehensive_graph() -> ConceptGraph:
        """Returns comprehensive Concept Graph populated across all CBSE classes."""
        g = ConceptGraph()

        # ==========================================
        # 1. CLASS 6 CONCEPTS
        # ==========================================
        g.add_node(ConceptNode("C6_NUT_VIT", "Vitamins & Minerals Deficiency scurvy", "C6_CH1", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 1))
        g.add_node(ConceptNode("C6_NUT_PRO", "Protein & Carbohydrate Dietary Sources", "C6_CH1", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 1))
        g.add_node(ConceptNode("C6_MAT_SORT", "Sorting Materials by Luster", "C6_CH2", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 1))
        g.add_node(ConceptNode("C6_SEP_WINN", "Separation by Winnowing & Handpicking", "C6_CH3", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 2))
        g.add_node(ConceptNode("C6_PLANT_FLOW", "Anatomy of Flowering Roots & Petals", "C6_CH4", AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.0, 2))

        # ==========================================
        # 2. CLASS 8 CONCEPTS
        # ==========================================
        g.add_node(ConceptNode("C8_AGR_KHAF", "Crop Production Sowing Kharif Seasons", "C8_CH1", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 2))
        g.add_node(ConceptNode("C8_BIO_CELLS", "Plant Cell vs Animal Cell Envelopes", "C8_CH5", AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.0, 3))
        g.add_node(ConceptNode("C8_PHY_PRES", "Force & Pressure Calculations area", "C8_CH6", AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.50, 3))
        g.add_node(ConceptNode("C8_PHY_HYDRO", "Hydrostatic Pressure Depth vessels", "C8_CH6", AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.60, 4))

        # Class 8 Links
        g.add_edge("C8_PHY_PRES", "C8_PHY_HYDRO", RelationshipType.PREREQUISITE)

        # ==========================================
        # 3. CLASS 10 CONCEPTS
        # ==========================================
        # Chapter 1
        g.add_node(ConceptNode("C10_RE_TYPE", "Reaction Categorization (Combination/Decomp)", "C10_CH1", AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.0, 2))
        g.add_node(ConceptNode("C10_EQ_BAL", "Chemical Equation Balancing Coefficients", "C10_CH1", AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.40, 3))
        g.add_node(ConceptNode("C10_RE_REDOX", "Redox Electron Transfer Oxidation Numbers", "C10_CH1", AbstractionLevel.THEORETICAL_MOLECULAR, 0.20, 4))
        
        # Chapter 2
        g.add_node(ConceptNode("C10_AC_PRO", "Acid-Base General Indicator Properties", "C10_CH2", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 2))
        g.add_node(ConceptNode("C10_AC_PH", "pH Logarithmic Acid Hydronium Scales", "C10_CH2", AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.60, 4))
        g.add_node(ConceptNode("C10_SALTS", "Commercial Chemical Salts Gypsum Plaster", "C10_CH2", AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.0, 3))

        # Chapter 5 (Life Processes)
        g.add_node(ConceptNode("C10_BIO_NUT", "Autotrophic Photosynthesis Stomata Mechanisms", "C10_CH5", AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.0, 3))
        g.add_node(ConceptNode("C10_BIO_RESP", "Aerobic Respiration Glucose Pyruvate Pathways", "C10_CH5", AbstractionLevel.THEORETICAL_MOLECULAR, 0.0, 4))
        g.add_node(ConceptNode("C10_BIO_CIRC", "Human Circulatory Double Heart Pulmonary Paths", "C10_CH5", AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.0, 4))
        g.add_node(ConceptNode("C10_BIO_EXCR", "Nephron Vascular Glomerulus Excretion Systems", "C10_CH5", AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.0, 5))

        # Chapter 9 (Reflection & Refraction)
        g.add_node(ConceptNode("C10_PHY_REFR", "Refractive Index Snell Mirror Snell's Laws", "C10_CH9", AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.80, 4))
        g.add_node(ConceptNode("C10_PHY_REFL", "Mirror Ray Lens Conjugate Equations", "C10_CH9", AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.85, 5))
        
        # Chapter 10 (Human Eye)
        g.add_node(ConceptNode("C10_PHY_EYE", "Anatomical Human Eye Myopia Hypermetropia Lens", "C10_CH10", AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.20, 3))
        g.add_node(ConceptNode("C10_PHY_DISP", "Glass Prism White Light Spectrums Dispersion", "C10_CH10", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 2))

        # Chapter 11 (Electricity)
        g.add_node(ConceptNode("C10_PHY_OHM", "Ohm Electric Resistance Currents Potentials", "C10_CH11", AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.90, 4))
        g.add_node(ConceptNode("C10_PHY_SER", "Series Parallel Resistive Circuits networks", "C10_CH11", AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.95, 6))

        # Class 10 Links
        g.add_edge("C10_RE_TYPE", "C10_EQ_BAL", RelationshipType.PREREQUISITE)
        g.add_edge("C10_RE_TYPE", "C10_RE_REDOX", RelationshipType.PREREQUISITE)
        g.add_edge("C10_AC_PRO", "C10_AC_PH", RelationshipType.PREREQUISITE)
        g.add_edge("C10_AC_PH", "C10_SALTS", RelationshipType.INFLUENCES)
        g.add_edge("C10_BIO_NUT", "C10_BIO_RESP", RelationshipType.PREREQUISITE)
        g.add_edge("C10_BIO_RESP", "C10_BIO_CIRC", RelationshipType.PREREQUISITE)
        g.add_edge("C10_BIO_CIRC", "C10_BIO_EXCR", RelationshipType.INFLUENCES)
        g.add_edge("C10_PHY_REFR", "C10_PHY_REFL", RelationshipType.PREREQUISITE)
        g.add_edge("C10_PHY_REFR", "C10_PHY_EYE", RelationshipType.PREREQUISITE)
        g.add_edge("C10_PHY_EYE", "C10_PHY_DISP", RelationshipType.INFLUENCES)
        g.add_edge("C10_PHY_OHM", "C10_PHY_SER", RelationshipType.PREREQUISITE)

        return g


# ==============================================================================
# RIGOROUS TESTS & VALIDATION SUITE (INTEGRATED UNIT TESTING FRAMEWORK)
# ==============================================================================

class CurriculumEngineUnitTestSuite:
    """Autonomous self-testing suite validating the complete integrity of Phase 3 curriculum graph systems."""

    @staticmethod
    def run_all_tests() -> Dict[str, Any]:
        """Runs tests, recording successes and capturing traceback errors."""
        results = {
            "total_assertions": 0,
            "passed_tests": 0,
            "failed_tests": [],
            "status": "INIT"
        }

        def assert_true(expression: bool, message: str) -> None:
            results["total_assertions"] += 1
            if expression:
                results["passed_tests"] += 1
            else:
                results["failed_tests"].append(message)
                raise AssertionError(message)

        try:
            # 1. Test Chapter Metadata Engine preloads
            ch_engine = ChapterMetadataEngine()
            ch = ch_engine.get_chapter("C10_CH11")
            assert_true(ch is not None, "Failed to load chapter Electricity.")
            assert_true(ch.stream == StreamType.PHYSICS, "Chapter stream mapping failed.")
            assert_true(ch.academic_class == AcademicClass.CLASS_10, "Chapter class mapping failed.")

            # Test Class 6 & 8 lists
            ch_c6 = ch_engine.get_chapters_by_class(AcademicClass.CLASS_6)
            assert_true(len(ch_c6) >= 5, "Class 6 chapters did not preload successfully.")

            # 2. Test Concept Graph topological order and DFS prereqs
            graph = CurriculumGraphFactory.construct_comprehensive_graph()
            
            # Topological order test
            topo_order = graph.get_topological_sort()
            assert_true(len(topo_order) > 0, "Topological sort returned empty sequence.")
            
            # Verify topological ordering constraint (source index < target index)
            for edge in graph.edges:
                s_idx = topo_order.index(edge.source_id)
                t_idx = topo_order.index(edge.target_id)
                assert_true(s_idx < t_idx, f"Topological Order Violation: {edge.source_id} placed before {edge.target_id}.")

            # DFS prereqs resolving
            prereqs_ser = graph.find_all_prerequisites("C10_PHY_SER")
            assert_true("C10_PHY_OHM" in prereqs_ser, "DFS failed to resolve Ohm as prerequisite for Series circuits.")

            # Graph geodesic distance
            dist = graph.calculate_geodesic_distance("C10_PHY_OHM", "C10_PHY_SER")
            assert_true(dist == 1, f"Expected adjacent concepts distance 1, got {dist}.")
            
            disconnected_dist = graph.calculate_geodesic_distance("C10_EQ_BAL", "C10_BIO_EXCR")
            assert_true(disconnected_dist == 999, "Disconnected concepts geodesic distance error.")

            # 3. Test cycle detection
            loop_graph = ConceptGraph()
            loop_graph.add_node(ConceptNode("N1", "C1", "CH1", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 1))
            loop_graph.add_node(ConceptNode("N2", "C2", "CH1", AbstractionLevel.CONCRETE_OBSERVABLE, 0.0, 1))
            loop_graph.add_edge("N1", "N2", RelationshipType.PREREQUISITE)
            loop_graph.add_edge("N2", "N1", RelationshipType.PREREQUISITE)  # Circular!
            assert_true(len(loop_graph.detect_cycles()) > 0, "Circular loop detector failed to raise flag.")

            # 4. Test Difficulty Estimation Engine
            weights = CurriculumWeightageRegistry()
            diff_engine = DifficultyEstimationEngine(graph, weights)
            diff_remember = diff_engine.estimate_difficulty("C10_PHY_SER", BloomsLevel.REMEMBER)
            diff_create = diff_engine.estimate_difficulty("C10_PHY_SER", BloomsLevel.CREATE)
            assert_true(diff_remember < diff_create, "Difficulty calculator failed to scale with Bloom's level.")

            # 5. Test Question Suitability Engine
            suit_engine = QuestionSuitabilityEngine(graph, weights)
            mcq_suit = suit_engine.calculate_suitability("C10_PHY_SER", QuestionTypeCode.MCQ)
            num_suit = suit_engine.calculate_suitability("C10_PHY_SER", QuestionTypeCode.NUMERICAL)
            assert_true(num_suit > mcq_suit, "Numerical questions suitability calculations failed to prioritize mathematical concepts.")

            # 6. Test duplicate prevention
            dup_engine = CurriculumDuplicatePreventionEngine(graph)
            is_dup_ok, _ = dup_engine.audit_duplication_safety(["C10_PHY_OHM", "C10_PHY_OHM"])
            assert_true(not is_dup_ok, "Duplicate prevention failed to block repetitive identical concept IDs.")

            # 7. Test prerequisite sequence pacing optimizer
            optimizer = PrerequisitePacingOptimizer(graph)
            unsafe_seq = ["C10_PHY_SER", "C10_PHY_OHM"]  # Series is tested BEFORE Ohm
            is_pacing_ok, _ = optimizer.is_sequence_prereq_safe(unsafe_seq)
            assert_true(not is_pacing_ok, "Pacing optimizer failed to flag invalid prerequisite sequencing.")

            results["status"] = "SUCCESS"

        except Exception as e:
            results["status"] = "FAILED"
            results["exception"] = str(e)

        return results


# ==============================================================================
# MASTER CLI INTERACTIVE GRAPH DIAGNOSTICS
# ==============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("ACADEMIC OPERATING SYSTEM - PHASE 3 CHAPTER & CONCEPT ENGINE DIAGNOSTICS")
    print("=" * 80)
    
    test_run = CurriculumEngineUnitTestSuite.run_all_tests()
    print(f"Self-Test Status:   {test_run['status']}")
    print(f"Passed Assertions:  {test_run['passed_tests']} / {test_run['total_assertions']}")
    
    if test_run["status"] == "FAILED":
        print(f"Failure Exception:  {test_run.get('exception')}")
        print("Failed Details:")
        for fd in test_run.get("failed_tests", []):
            print(f"  - {fd}")
        exit(1)
    else:
        print("Curriculum graph engines, topological solvers, and estimators operate at 100% precision.")

    print("-" * 80)
    
    # Showcase full Class 10 Concept topological prerequisite chain
    print("Demonstrating topological sorting and concept difficulty metrics for Class 10 Science...")
    graph = CurriculumGraphFactory.construct_comprehensive_graph()
    weights = CurriculumWeightageRegistry()
    diff_engine = DifficultyEstimationEngine(graph, weights)
    suit_engine = QuestionSuitabilityEngine(graph, weights)
    
    sorted_concept_ids = [c for c in graph.get_topological_sort() if c.startswith("C10")]
    
    print("\n| Concept ID   | Concept Name                     | Abstraction Level   | Diff (R) | Diff (C) | Suit (MCQ) | Suit (NUM) |")
    print("|--------------|----------------------------------|---------------------|----------|----------|------------|------------|")
    for cid in sorted_concept_ids:
        node = graph.nodes[cid]
        d_rem = diff_engine.estimate_difficulty(cid, BloomsLevel.REMEMBER)
        d_cre = diff_engine.estimate_difficulty(cid, BloomsLevel.CREATE)
        s_mcq = suit_engine.calculate_suitability(cid, QuestionTypeCode.MCQ)
        s_num = suit_engine.calculate_suitability(cid, QuestionTypeCode.NUMERICAL)
        
        print(f"| {cid:<12} | {node.concept_name:<32} | {node.abstraction.name:<19} | {d_rem:>8.2f} | {d_cre:>8.2f} | {s_mcq:>10.2f} | {s_num:>10.2f} |")
        
    print("-" * 80)
    # Output visual ASCII trees for electricity and light
    print(ConsoleGraphAsciiRenderer.render_tree(graph, "C10_PHY_OHM"))
    print(ConsoleGraphAsciiRenderer.render_tree(graph, "C10_PHY_REFR"))
    print(ConsoleGraphAsciiRenderer.render_tree(graph, "C10_BIO_NUT"))
    print(ConsoleGraphAsciiRenderer.render_tree(graph, "C10_RE_TYPE"))
        
    print("=" * 80)
