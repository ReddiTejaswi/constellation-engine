"""Historical discovery benchmarks.

A benchmark provides:
- a research question
- a cutoff year (literature past this year is excluded during retrieval)
- a list of "reference intermediate connections" that later became
  significant on the path to the breakthrough (as entity pairs)
- optionally the reference final hypothesis

We evaluate how many of those intermediate connections the pipeline
reconstructed from the pre-cutoff literature, and how similar its
candidate hypotheses are to the known reference. We do NOT claim this
means the AI would have made the discovery.
"""
from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List

from backend.agents.pipeline import run_pipeline
from backend.graph.builder import _norm

logger = logging.getLogger(__name__)


BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "optogenetics": {
        "id": "optogenetics",
        "title": "Optogenetics",
        "cutoff_year": 2004,
        "question": (
            "Could microbial light-sensitive proteins be used to control the activity "
            "of individual neurons with light?"
        ),
        "reference_entities": [
            "channelrhodopsin", "bacteriorhodopsin", "halorhodopsin",
            "chlamydomonas reinhardtii", "ion channel", "neuron",
            "action potential", "membrane potential", "light-gated ion channel",
        ],
        "reference_connections": [
            ["channelrhodopsin", "ion channel"],
            ["channelrhodopsin", "light"],
            ["light-gated ion channel", "neuron"],
            ["ion channel", "action potential"],
            ["ion channel", "membrane potential"],
        ],
        "reference_hypothesis": (
            "Expressing a light-gated microbial ion channel in neurons would allow "
            "optical control of action potentials with millisecond precision."
        ),
    },
    "helicobacter_ulcers": {
        "id": "helicobacter_ulcers",
        "title": "Helicobacter pylori and peptic ulcers",
        "cutoff_year": 1983,
        "question": "What causes peptic ulcers and chronic gastritis?",
        "reference_entities": [
            "helicobacter pylori", "campylobacter", "spiral bacteria",
            "gastric mucosa", "chronic gastritis", "peptic ulcer",
            "stomach acid", "antibiotics",
        ],
        "reference_connections": [
            ["spiral bacteria", "gastric mucosa"],
            ["chronic gastritis", "peptic ulcer"],
            ["spiral bacteria", "chronic gastritis"],
        ],
        "reference_hypothesis": (
            "A spiral bacterium colonizing the gastric mucosa causes chronic gastritis "
            "and peptic ulcers, and antibiotic eradication should resolve them."
        ),
    },
}


def list_benchmarks() -> List[Dict[str, Any]]:
    return [{"id": b["id"], "title": b["title"], "cutoff_year": b["cutoff_year"]} for b in BENCHMARKS.values()]


async def run_benchmark(bench_id: str) -> Dict[str, Any]:
    if bench_id not in BENCHMARKS:
        raise KeyError(bench_id)
    spec = BENCHMARKS[bench_id]
    report = await run_pipeline(
        spec["question"],
        year_cutoff=spec["cutoff_year"],
    )
    metrics = _evaluate(report, spec)
    return {
        "benchmark": spec,
        "report": report.model_dump(),
        "metrics": metrics,
    }


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _evaluate(report, spec) -> Dict[str, Any]:
    labels = {n.id: n.label for n in report.graph.nodes}
    norm_labels = {nid: _norm(lbl) for nid, lbl in labels.items()}

    ref_entities = [_norm(e) for e in spec["reference_entities"]]
    entity_recovered = []
    for e in ref_entities:
        hit = any(e in nl or nl in e for nl in norm_labels.values())
        entity_recovered.append({"entity": e, "recovered": hit})

    # multi-hop connection recovery
    ref_pairs = [(_norm(a), _norm(b)) for a, b in spec["reference_connections"]]
    conn_recovered = []
    conn_paths = report.connections
    for a, b in ref_pairs:
        found_direct = False
        found_multihop = False
        for c in conn_paths:
            labels_norm = [_norm(l) for l in c.path_labels]
            match_a = any(a in ln or ln in a for ln in labels_norm)
            match_b = any(b in ln or ln in b for ln in labels_norm)
            if match_a and match_b:
                if c.direct_evidence:
                    found_direct = True
                else:
                    found_multihop = True
        conn_recovered.append({"pair": [a, b], "direct": found_direct, "multihop": found_multihop})

    # hypothesis similarity vs reference
    ref_hyp = spec.get("reference_hypothesis", "")
    hyp_scores = [
        {"id": h.id, "similarity": _similar(h.statement, ref_hyp), "statement": h.statement}
        for h in report.hypotheses
    ]
    best = max((s["similarity"] for s in hyp_scores), default=0.0)

    return {
        "entities_total": len(ref_entities),
        "entities_recovered": sum(1 for x in entity_recovered if x["recovered"]),
        "entity_detail": entity_recovered,
        "connections_total": len(ref_pairs),
        "connections_multihop_recovered": sum(1 for x in conn_recovered if x["multihop"] or x["direct"]),
        "connections_direct_recovered": sum(1 for x in conn_recovered if x["direct"]),
        "connection_detail": conn_recovered,
        "best_hypothesis_similarity": round(best, 3),
        "hypothesis_similarities": hyp_scores,
        "note": (
            "Metrics measure the ability to CONNECT dots from pre-cutoff literature. "
            "They do NOT indicate that the AI would have discovered the breakthrough."
        ),
    }
