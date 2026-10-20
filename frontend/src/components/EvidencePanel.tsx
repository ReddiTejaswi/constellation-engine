import type { DiscoveryReport, Finding, GraphEdge, Paper } from "../types";

function Pill({ s }: { s: string }) {
  return <span className={`pill ${s}`}>{s}</span>;
}

export function EvidencePanel({
  report,
  edgeId,
  findings,
  papers,
}: {
  report: DiscoveryReport;
  edgeId: string | null;
  findings: Record<string, Finding>;
  papers: Record<string, Paper>;
}) {
  if (!edgeId) {
    return (
      <div className="card">
        <div className="meta">Click an edge in the graph to see its evidence and provenance.</div>
      </div>
    );
  }
  const e: GraphEdge | undefined = report.graph.edges.find((x) => x.id === edgeId);
  if (!e) return <div className="card">Edge not found.</div>;
  const srcLabel = report.graph.nodes.find((n) => n.id === e.source)?.label ?? e.source;
  const tgtLabel = report.graph.nodes.find((n) => n.id === e.target)?.label ?? e.target;

  const supportingFindings = e.supporting_findings
    .map((fid) => findings[fid])
    .filter(Boolean);
  const contradictions = report.contradictions.filter(
    (c) => (c.subject === e.source && c.object === e.target) ||
           (c.subject === e.target && c.object === e.source)
  );

  return (
    <div className="card">
      <div className="title">
        {srcLabel} <code>{e.relationship}</code> {tgtLabel}
      </div>
      <div className="meta">
        <Pill s={e.status} />
        confidence {e.confidence.toFixed(2)} · {e.papers.length} source(s)
      </div>
      <div className="badges">
        {e.evidence_levels.map((lv) => (
          <span key={lv} className="badge">{lv}</span>
        ))}
      </div>
      <h4 style={{ marginTop: 12, marginBottom: 6 }}>Supporting evidence</h4>
      {supportingFindings.length === 0 && <div className="meta">No findings linked.</div>}
      {supportingFindings.map((f, i) => {
        const p = papers[f.source_id];
        return (
          <div key={i} className="card" style={{ background: "var(--panel-2)" }}>
            <div className="meta">
              {p?.url ? <a href={p.url} target="_blank" rel="noreferrer">{p.title}</a> : (p?.title ?? f.source_id)}
            </div>
            <div className="meta" style={{ fontSize: 11 }}>
              {p?.authors?.slice(0, 3).join(", ")}{p && p.authors && p.authors.length > 3 ? " et al." : ""} · {p?.year ?? "n/a"} · {f.source_id}
            </div>
            {f.source_quote && (
              <div style={{ marginTop: 6, fontStyle: "italic", fontSize: 12 }}>
                "{f.source_quote}"
              </div>
            )}
            <div className="badges" style={{ marginTop: 6 }}>
              <span className="badge">{f.evidence_level}</span>
              {f.organism && <span className="badge">{f.organism}</span>}
              {f.system && <span className="badge">{f.system}</span>}
            </div>
          </div>
        );
      })}
      {contradictions.length > 0 && (
        <>
          <h4 style={{ marginTop: 12, marginBottom: 6 }}>Contradictions</h4>
          {contradictions.map((c, i) => (
            <div key={i} className="card" style={{ background: "var(--panel-2)" }}>
              <div className="meta">
                supporting: {c.supporting.join(", ")}; contradicting: {c.contradicting.join(", ")}
              </div>
              <ul>
                {c.possible_explanations.map((x, j) => <li key={j}>{x}</li>)}
              </ul>
              <div className="meta">Resolution: {c.resolution} · Confidence: {c.confidence}</div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
