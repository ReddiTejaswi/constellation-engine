"""Pydantic schemas used between pipeline stages.

Agents communicate exclusively via these structured objects. The LLM is
never allowed to control storage or the graph directly: every structured
output is validated here before it enters any downstream stage.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class EvidenceStatus(str, Enum):
    ESTABLISHED = "ESTABLISHED"
    SUPPORTED = "SUPPORTED"
    INFERRED = "INFERRED"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


class EvidenceLevel(str, Enum):
    HUMAN_CLINICAL = "human_clinical"
    HUMAN_OBSERVATIONAL = "human_observational"
    HUMAN_TISSUE = "human_tissue"
    ANIMAL = "animal"
    ORGANOID = "organoid"
    CELL_CULTURE = "cell_culture"
    IN_VITRO = "in_vitro_biochemical"
    COMPUTATIONAL = "computational"
    THEORETICAL = "theoretical"
    UNKNOWN = "unknown"


class EntityType(str, Enum):
    GENE = "gene"
    PROTEIN = "protein"
    MOLECULE = "molecule"
    PATHWAY = "pathway"
    CELL = "cell"
    TISSUE = "tissue"
    DISEASE = "disease"
    DRUG = "drug"
    PHENOTYPE = "phenotype"
    BIOPROCESS = "biological_process"
    EXPERIMENT = "experiment"
    PAPER = "paper"
    RESEARCHER = "researcher"
    CONCEPT = "concept"


# ------------------------------- Question -------------------------------


class DecomposedQuestion(BaseModel):
    original_question: str
    diseases: List[str] = []
    genes: List[str] = []
    proteins: List[str] = []
    molecules: List[str] = []
    pathways: List[str] = []
    cell_types: List[str] = []
    tissues: List[str] = []
    phenotypes: List[str] = []
    biological_processes: List[str] = []
    drugs: List[str] = []
    mechanisms: List[str] = []
    experimental_methods: List[str] = []
    synonyms: Dict[str, List[str]] = {}
    search_queries: List[str] = Field(
        default_factory=list,
        description="Concrete literature search queries derived from the decomposition.",
    )


# ------------------------------- Retrieval -------------------------------


class Paper(BaseModel):
    identifier: str = Field(..., description="Stable id e.g. PMID:12345 or DOI")
    title: str
    authors: List[str] = []
    publication_date: Optional[str] = None  # ISO YYYY or YYYY-MM-DD
    year: Optional[int] = None
    source: str  # pubmed, europepmc, biorxiv, ...
    url: Optional[str] = None
    abstract: Optional[str] = None
    full_text: Optional[str] = None
    journal: Optional[str] = None
    query: Optional[str] = None  # which decomposed query returned this


# ------------------------------- Evidence -------------------------------


class Finding(BaseModel):
    """A single atomic scientific finding extracted from a paper.

    Unknown fields must stay None/empty. The extractor is instructed to
    refuse to invent missing information.
    """

    subject: str
    subject_type: Optional[EntityType] = None
    relationship: str
    object: str
    object_type: Optional[EntityType] = None
    evidence_type: Optional[str] = None  # experimental, review, computational, ...
    evidence_level: EvidenceLevel = EvidenceLevel.UNKNOWN
    organism: Optional[str] = None
    system: Optional[str] = None  # e.g. "cell culture", "mouse model", "cohort n=423"
    source_id: str
    source_quote: Optional[str] = None
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    status: EvidenceStatus = EvidenceStatus.SUPPORTED


# ------------------------------- Graph -------------------------------


class GraphNode(BaseModel):
    id: str
    label: str
    type: EntityType
    mentions: int = 1
    aliases: List[str] = []


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship: str
    status: EvidenceStatus
    evidence_levels: List[EvidenceLevel] = []
    confidence: float = 0.5
    supporting_findings: List[str] = []  # Finding ids
    contradicting_findings: List[str] = []
    papers: List[str] = []  # Paper identifiers


class EvidenceGraph(BaseModel):
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []


# ------------------------------- Connections / contradictions / gaps -------


class Connection(BaseModel):
    path: List[str]  # node ids
    path_labels: List[str] = []
    relationships: List[str] = []
    status: EvidenceStatus
    rationale: str
    supporting_edges: List[str] = []
    direct_evidence: bool = False


class Contradiction(BaseModel):
    subject: str
    object: str
    supporting: List[str]  # Finding ids
    contradicting: List[str]
    possible_explanations: List[str] = []
    resolution: str = "Currently unresolved."
    confidence: Literal["Low", "Moderate", "High"] = "Moderate"


class ResearchGap(BaseModel):
    description: str
    missing_edge: Dict[str, str]  # {source, target, relationship}
    adjacent_evidence: List[str] = []  # edge ids that make the gap suggestive
    rationale: str


# ------------------------------- Hypothesis -------------------------------


class HypothesisCritique(BaseModel):
    weaknesses: List[str] = []
    alternative_explanations: List[str] = []
    contradictory_studies: List[str] = []
    correlation_vs_causation: Optional[str] = None
    species_differences: Optional[str] = None
    publication_bias: Optional[str] = None
    already_established: bool = False
    is_testable: bool = True
    support_score: float = 0.5
    contradiction_score: float = 0.0
    evidence_quality: Literal["High", "Moderate", "Low", "Speculative"] = "Moderate"
    novelty_score: float = 0.5
    testability_score: float = 0.5
    overall_confidence: Literal["High", "Moderate", "Low", "Speculative"] = "Moderate"


class Hypothesis(BaseModel):
    id: str
    statement: str
    rationale: str
    evidence_chain: List[str] = []  # edge ids / finding ids
    supporting_evidence: List[str] = []  # finding ids
    contradictory_evidence: List[str] = []
    missing_links: List[str] = []
    evidence_strength: Literal["High", "Moderate", "Low", "Speculative"] = "Moderate"
    novelty: str = "Unknown"
    testable_prediction: str
    suggested_experiment: str
    expected_if_correct: str
    expected_if_wrong: str
    status: EvidenceStatus = EvidenceStatus.HYPOTHESIS
    critique: Optional[HypothesisCritique] = None


# ------------------------------- Report -------------------------------


class DiscoveryReport(BaseModel):
    research_question: str
    decomposition: DecomposedQuestion
    papers: List[Paper]
    findings: List[Finding]
    graph: EvidenceGraph
    key_findings: List[str]
    connections: List[Connection]
    contradictions: List[Contradiction]
    gaps: List[ResearchGap]
    hypotheses: List[Hypothesis]
    confidence_summary: Literal["High", "Moderate", "Low", "Speculative"] = "Moderate"
    disclaimer: str = (
        "These hypotheses are AI-generated research suggestions based on the "
        "retrieved literature. They are not experimentally validated scientific "
        "conclusions and require expert review and experimental testing."
    )
    telemetry: Dict[str, Any] = {}
