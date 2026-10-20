export type EvidenceStatus =
  | "ESTABLISHED"
  | "SUPPORTED"
  | "INFERRED"
  | "HYPOTHESIS"
  | "UNKNOWN";

export interface Paper {
  identifier: string;
  title: string;
  authors: string[];
  publication_date?: string | null;
  year?: number | null;
  source: string;
  url?: string | null;
  abstract?: string | null;
  journal?: string | null;
}

export interface Finding {
  subject: string;
  relationship: string;
  object: string;
  evidence_type?: string | null;
  evidence_level: string;
  organism?: string | null;
  system?: string | null;
  source_id: string;
  source_quote?: string | null;
  confidence: number;
  status: EvidenceStatus;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  mentions: number;
  aliases: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relationship: string;
  status: EvidenceStatus;
  evidence_levels: string[];
  confidence: number;
  supporting_findings: string[];
  contradicting_findings: string[];
  papers: string[];
}

export interface Connection {
  path: string[];
  path_labels: string[];
  relationships: string[];
  status: EvidenceStatus;
  rationale: string;
  supporting_edges: string[];
  direct_evidence: boolean;
}

export interface Contradiction {
  subject: string;
  object: string;
  supporting: string[];
  contradicting: string[];
  possible_explanations: string[];
  resolution: string;
  confidence: "Low" | "Moderate" | "High";
}

export interface ResearchGap {
  description: string;
  missing_edge: { source: string; target: string; relationship: string };
  adjacent_evidence: string[];
  rationale: string;
}

export interface HypothesisCritique {
  weaknesses: string[];
  alternative_explanations: string[];
  contradictory_studies: string[];
  correlation_vs_causation?: string | null;
  species_differences?: string | null;
  publication_bias?: string | null;
  already_established: boolean;
  is_testable: boolean;
  support_score: number;
  contradiction_score: number;
  evidence_quality: "High" | "Moderate" | "Low" | "Speculative";
  novelty_score: number;
  testability_score: number;
  overall_confidence: "High" | "Moderate" | "Low" | "Speculative";
}

export interface Hypothesis {
  id: string;
  statement: string;
  rationale: string;
  evidence_chain: string[];
  supporting_evidence: string[];
  contradictory_evidence: string[];
  missing_links: string[];
  evidence_strength: "High" | "Moderate" | "Low" | "Speculative";
  novelty: string;
  testable_prediction: string;
  suggested_experiment: string;
  expected_if_correct: string;
  expected_if_wrong: string;
  status: EvidenceStatus;
  critique?: HypothesisCritique | null;
}

export interface DiscoveryReport {
  research_question: string;
  decomposition: any;
  papers: Paper[];
  findings: Finding[];
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  key_findings: string[];
  connections: Connection[];
  contradictions: Contradiction[];
  gaps: ResearchGap[];
  hypotheses: Hypothesis[];
  confidence_summary: "High" | "Moderate" | "Low" | "Speculative";
  disclaimer: string;
  telemetry: Record<string, number>;
}

export interface StreamEvent {
  stage: string;
  status: "started" | "completed" | "error";
  message: string;
  data: any;
  ts: number;
}
