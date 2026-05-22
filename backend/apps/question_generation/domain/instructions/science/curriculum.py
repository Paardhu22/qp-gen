"""
Science curriculum graph and weight profiles.
"""

from collections import deque
from functools import lru_cache
from typing import Dict, List, Set, Tuple

from ...datatypes import ChapterMetadata, ConceptEdge, ConceptNode, ConceptWeightProfile
from ...enums import AbstractionLevel, AcademicClass, BloomsLevel, RelationshipType, StreamType
from ...exceptions import ConceptNotFoundError, CyclicDependencyError


class ConceptGraph:
    def __init__(self) -> None:
        self.nodes: Dict[str, ConceptNode] = {}
        self.edges: List[ConceptEdge] = []
        self.adjacency: Dict[str, List[str]] = {}

    def add_node(self, node: ConceptNode) -> None:
        self.nodes[node.concept_id] = node
        if node.concept_id not in self.adjacency:
            self.adjacency[node.concept_id] = []

    def add_edge(self, edge: ConceptEdge) -> None:
        self.edges.append(edge)
        if edge.source_id not in self.adjacency:
            self.adjacency[edge.source_id] = []
        self.adjacency[edge.source_id].append(edge.target_id)

    def detect_cycles(self) -> bool:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def _dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            for neighbor in self.adjacency.get(node_id, []):
                if neighbor not in visited:
                    if _dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node_id)
            return False

        for nid in self.nodes:
            if nid not in visited:
                if _dfs(nid):
                    return True
        return False

    def topological_sort(self) -> List[str]:
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        for edge in self.edges:
            if edge.target_id in in_degree:
                in_degree[edge.target_id] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result: List[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)
            for neighbor in self.adjacency.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.nodes):
            raise CyclicDependencyError("Topological sort incomplete - cycle detected.")
        return result

    def get_prerequisites(self, concept_id: str) -> List[str]:
        prereqs: List[str] = []
        for edge in self.edges:
            if edge.target_id == concept_id:
                prereqs.append(edge.source_id)
        return prereqs

    def get_dependents(self, concept_id: str) -> List[str]:
        return self.adjacency.get(concept_id, [])

    def bfs_distance(self, source: str, target: str) -> int:
        if source not in self.nodes or target not in self.nodes:
            return -1
        visited: Set[str] = {source}
        queue: deque = deque([(source, 0)])
        while queue:
            current, dist = queue.popleft()
            if current == target:
                return dist
            for neighbor in self.adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))
        return -1


class ChapterMetadataEngine:
    def __init__(self) -> None:
        self._chapters: Dict[str, ChapterMetadata] = {}
        self._initialize()

    def _initialize(self) -> None:
        chapters = [
            ChapterMetadata("C10_CH1", "Chemical Reactions and Equations", AcademicClass.CLASS_10, StreamType.CHEMISTRY, 1, 0.55, 0.40, 0.60),
            ChapterMetadata("C10_CH2", "Acids, Bases and Salts", AcademicClass.CLASS_10, StreamType.CHEMISTRY, 2, 0.60, 0.50, 0.50),
            ChapterMetadata("C10_CH5", "Life Processes", AcademicClass.CLASS_10, StreamType.BIOLOGY, 5, 0.65, 0.35, 0.65),
            ChapterMetadata("C10_CH9", "Light - Reflection and Refraction", AcademicClass.CLASS_10, StreamType.PHYSICS, 9, 0.70, 0.30, 0.70),
            ChapterMetadata("C10_CH11", "Electricity", AcademicClass.CLASS_10, StreamType.PHYSICS, 11, 0.75, 0.45, 0.55),
        ]
        for ch in chapters:
            self._chapters[ch.chapter_id] = ch

    def get_chapter(self, chapter_id: str) -> ChapterMetadata:
        if chapter_id not in self._chapters:
            raise ConceptNotFoundError(chapter_id)
        return self._chapters[chapter_id]

    def get_chapters_by_stream(self, stream: StreamType) -> List[ChapterMetadata]:
        return [ch for ch in self._chapters.values() if ch.primary_stream == stream]


class CurriculumWeightageRegistry:
    def __init__(self) -> None:
        self._profiles: Dict[str, ConceptWeightProfile] = {}
        self._initialize()

    def _initialize(self) -> None:
        defaults = [
            ConceptWeightProfile("C10_EQ_BAL", 0.80, 0.85, True, "CBSE.SC.10.1.1"),
            ConceptWeightProfile("C10_RE_TYPE", 0.75, 0.80, True, "CBSE.SC.10.1.2"),
            ConceptWeightProfile("C10_RE_REDOX", 0.65, 0.60, False, "CBSE.SC.10.1.3"),
            ConceptWeightProfile("C10_AC_PRO", 0.60, 0.70, False, "CBSE.SC.10.2.1"),
            ConceptWeightProfile("C10_AC_PH", 0.85, 0.90, True, "CBSE.SC.10.2.2"),
            ConceptWeightProfile("C10_SALTS", 0.55, 0.50, False, "CBSE.SC.10.2.3"),
            ConceptWeightProfile("C10_BIO_NUT", 0.70, 0.75, True, "CBSE.SC.10.5.1"),
            ConceptWeightProfile("C10_BIO_RESP", 0.60, 0.55, False, "CBSE.SC.10.5.2"),
            ConceptWeightProfile("C10_BIO_CIRC", 0.75, 0.80, True, "CBSE.SC.10.5.3"),
            ConceptWeightProfile("C10_BIO_EXCR", 0.65, 0.60, False, "CBSE.SC.10.5.4"),
            ConceptWeightProfile("C10_PHY_OHM", 0.90, 0.95, True, "CBSE.SC.10.11.1"),
            ConceptWeightProfile("C10_PHY_SER", 0.80, 0.85, True, "CBSE.SC.10.11.2"),
            ConceptWeightProfile("C10_PHY_REFR", 0.85, 0.90, True, "CBSE.SC.10.9.2"),
            ConceptWeightProfile("C10_PHY_REFL", 0.80, 0.85, True, "CBSE.SC.10.9.1"),
            ConceptWeightProfile("C10_PHY_EYE", 0.70, 0.75, True, "CBSE.SC.10.9.3"),
            ConceptWeightProfile("C10_PHY_DISP", 0.50, 0.45, False, "CBSE.SC.10.9.4"),
        ]
        for p in defaults:
            self._profiles[p.concept_id] = p

    def get_weight_profile(self, concept_id: str) -> ConceptWeightProfile:
        return self._profiles.get(concept_id, ConceptWeightProfile(concept_id, 0.5, 0.5, False, ""))


class CurriculumDuplicatePreventionEngine:
    def __init__(self, graph: ConceptGraph) -> None:
        self.graph = graph

    def audit_duplication_safety(self, concept_ids: List[str]) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        seen: Set[str] = set()
        for cid in concept_ids:
            if cid in seen:
                errors.append(f"Duplicate concept '{cid}' detected in paper.")
            seen.add(cid)
        return len(errors) == 0, errors


class DifficultyEstimationEngine:
    def __init__(self, graph: ConceptGraph, weights: CurriculumWeightageRegistry) -> None:
        self.graph = graph
        self.weights = weights

    def estimate_difficulty(self, concept_id: str, bloom_level: BloomsLevel) -> float:
        node = self.graph.nodes.get(concept_id)
        if not node:
            return 0.5

        bloom_weights = {
            BloomsLevel.REMEMBER: 0.15,
            BloomsLevel.UNDERSTAND: 0.30,
            BloomsLevel.APPLY: 0.50,
            BloomsLevel.ANALYZE: 0.70,
            BloomsLevel.EVALUATE: 0.85,
            BloomsLevel.CREATE: 0.95,
        }
        bloom_factor = bloom_weights.get(bloom_level, 0.5)

        prereq_count = len(self.graph.get_prerequisites(concept_id))
        depth_factor = min(prereq_count * 0.15, 0.40)

        numerical_factor = node.base_numerical_depth * 0.30
        reasoning_factor = min(node.base_reasoning_steps * 0.08, 0.30)

        raw = bloom_factor * 0.40 + depth_factor + numerical_factor + reasoning_factor
        return min(max(raw, 0.0), 1.0)


class PrerequisitePacingOptimizer:
    def __init__(self, graph: ConceptGraph) -> None:
        self.graph = graph

    def optimize_sequence(self, concept_ids: List[str]) -> List[str]:
        topo_order = self.graph.topological_sort()
        topo_index = {cid: idx for idx, cid in enumerate(topo_order)}
        filtered = [cid for cid in concept_ids if cid in topo_index]
        filtered.sort(key=lambda c: topo_index.get(c, 999))
        return filtered


class CurriculumGraphFactory:
    @staticmethod
    @lru_cache(maxsize=1)
    def construct_comprehensive_graph() -> ConceptGraph:
        graph = ConceptGraph()

        nodes = [
            ConceptNode("C10_EQ_BAL", "Chemical Equation Balancing Coefficients", AcademicClass.CLASS_10, StreamType.CHEMISTRY, AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.40, 3),
            ConceptNode("C10_RE_TYPE", "Reaction Categorization (Combination/Decomp)", AcademicClass.CLASS_10, StreamType.CHEMISTRY, AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.10, 2),
            ConceptNode("C10_RE_REDOX", "Redox Electron Transfer Oxidation Numbers", AcademicClass.CLASS_10, StreamType.CHEMISTRY, AbstractionLevel.THEORETICAL_MOLECULAR, 0.20, 4),
            ConceptNode("C10_AC_PRO", "Acid-Base General Indicator Properties", AcademicClass.CLASS_10, StreamType.CHEMISTRY, AbstractionLevel.CONCRETE_OBSERVABLE, 0.00, 1),
            ConceptNode("C10_AC_PH", "pH Logarithmic Acid Hydronium Scales", AcademicClass.CLASS_10, StreamType.CHEMISTRY, AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.60, 3),
            ConceptNode("C10_SALTS", "Commercial Chemical Salts Gypsum Plaster", AcademicClass.CLASS_10, StreamType.CHEMISTRY, AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.00, 2),
            ConceptNode("C10_BIO_NUT", "Autotrophic Photosynthesis Stomata Mechanisms", AcademicClass.CLASS_10, StreamType.BIOLOGY, AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.00, 2),
            ConceptNode("C10_BIO_RESP", "Aerobic Respiration Glucose Pyruvate Pathways", AcademicClass.CLASS_10, StreamType.BIOLOGY, AbstractionLevel.THEORETICAL_MOLECULAR, 0.00, 4),
            ConceptNode("C10_BIO_CIRC", "Human Circulatory Double Heart Pulmonary Paths", AcademicClass.CLASS_10, StreamType.BIOLOGY, AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.00, 3),
            ConceptNode("C10_BIO_EXCR", "Nephron Vascular Glomerulus Excretion Systems", AcademicClass.CLASS_10, StreamType.BIOLOGY, AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.00, 3),
            ConceptNode("C10_PHY_OHM", "Ohm Electric Resistance Currents Potentials", AcademicClass.CLASS_10, StreamType.PHYSICS, AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.90, 3),
            ConceptNode("C10_PHY_SER", "Series Parallel Resistive Circuits networks", AcademicClass.CLASS_10, StreamType.PHYSICS, AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.95, 4),
            ConceptNode("C10_PHY_REFR", "Refractive Index Snell Mirror Snell's Laws", AcademicClass.CLASS_10, StreamType.PHYSICS, AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.80, 3),
            ConceptNode("C10_PHY_REFL", "Mirror Ray Lens Conjugate Equations", AcademicClass.CLASS_10, StreamType.PHYSICS, AbstractionLevel.QUANTITATIVE_FUNCTIONAL, 0.85, 3),
            ConceptNode("C10_PHY_EYE", "Anatomical Human Eye Myopia Hypermetropia Lens", AcademicClass.CLASS_10, StreamType.PHYSICS, AbstractionLevel.MECHANISTIC_SYSTEMIC, 0.20, 2),
            ConceptNode("C10_PHY_DISP", "Glass Prism White Light Spectrums Dispersion", AcademicClass.CLASS_10, StreamType.PHYSICS, AbstractionLevel.CONCRETE_OBSERVABLE, 0.00, 1),
        ]
        for node in nodes:
            graph.add_node(node)

        edges = [
            ConceptEdge("C10_RE_TYPE", "C10_EQ_BAL", RelationshipType.PREREQUISITE, 0.9),
            ConceptEdge("C10_RE_TYPE", "C10_RE_REDOX", RelationshipType.PREREQUISITE, 0.8),
            ConceptEdge("C10_AC_PRO", "C10_AC_PH", RelationshipType.PREREQUISITE, 0.9),
            ConceptEdge("C10_AC_PH", "C10_SALTS", RelationshipType.EXTENDS, 0.7),
            ConceptEdge("C10_BIO_NUT", "C10_BIO_RESP", RelationshipType.PREREQUISITE, 0.9),
            ConceptEdge("C10_BIO_RESP", "C10_BIO_CIRC", RelationshipType.PREREQUISITE, 0.8),
            ConceptEdge("C10_BIO_CIRC", "C10_BIO_EXCR", RelationshipType.PREREQUISITE, 0.7),
            ConceptEdge("C10_PHY_OHM", "C10_PHY_SER", RelationshipType.PREREQUISITE, 0.95),
            ConceptEdge("C10_PHY_REFR", "C10_PHY_EYE", RelationshipType.PREREQUISITE, 0.85),
            ConceptEdge("C10_PHY_EYE", "C10_PHY_DISP", RelationshipType.PREREQUISITE, 0.7),
            ConceptEdge("C10_PHY_REFR", "C10_PHY_REFL", RelationshipType.EXTENDS, 0.8),
        ]
        for edge in edges:
            graph.add_edge(edge)

        return graph
