import type { DiscoveryReport, Hypothesis } from "../types";

function Pill({ s }: { s: string }) {
  return <span className={`pill ${s}`}>{s}</span>;
}

export function HypothesisPanel({ report }: { report: DiscoveryReport }) {
  if (report.hypotheses.length === 0) {
    return (
      <div className="card">
        <div className="meta">No hypotheses were produced. Insufficient evidence.</div>
      </div>
    );
  }
  return (
    <>
      {report.hypotheses.map((h: Hypothesis) => (
        <div key={h.id} className="card">
          <div className="title">
            <Pill s={h.status} /> {h.id}: {h.statement}
          </div>
          <div className="meta">
            Evidence strength: <b>{h.evidence_strength}</b> · Novelty: {h.novelty}
          </div>
          <details open>
            <summary>Rationale</summary>
            <div className="meta" style={{ marginTop: 6 }}>{h.rationale}</div>
          </details>
          <details>
            <summary>Evidence chain</summary>
            <ul>
              {h.evidence_chain.map((e, i) => <li key={i}><code>{e}</code></li>)}
            </ul>
            {h.missing_links.length > 0 && (
              <>
                <div className="meta">Missing links:</div>
                <ul>
                  {h.missing_links.map((m, i) => <li key={i}>{m}</li>)}
                </ul>
              </>
            )}
          </details>
          <details>
            <summary>Testable prediction & suggested experiment</summary>
            <div className="meta" style={{ marginTop: 6 }}><b>Predict:</b> {h.testable_prediction}</div>
            <div className="meta"><b>Experiment:</b> {h.suggested_experiment}</div>
            <div className="meta"><b>If correct:</b> {h.expected_if_correct}</div>
            <div className="meta"><b>If wrong:</b> {h.expected_if_wrong}</div>
          </details>
          {h.critique && (
            <details>
              <summary>Critique (adversarial review)</summary>
              <div className="badges" style={{ marginTop: 6 }}>
                <span className="badge">support {h.critique.support_score.toFixed(2)}</span>
                <span className="badge">contradiction {h.critique.contradiction_score.toFixed(2)}</span>
                <span className="badge">novelty {h.critique.novelty_score.toFixed(2)}</span>
                <span className="badge">testability {h.critique.testability_score.toFixed(2)}</span>
                <span className="badge">quality: {h.critique.evidence_quality}</span>
                <span className="badge">overall: {h.critique.overall_confidence}</span>
              </div>
              {h.critique.weaknesses.length > 0 && (
                <>
                  <div className="meta" style={{ marginTop: 6 }}>Weaknesses:</div>
                  <ul>{h.critique.weaknesses.map((w, i) => <li key={i}>{w}</li>)}</ul>
                </>
              )}
              {h.critique.alternative_explanations.length > 0 && (
                <>
                  <div className="meta">Alternative explanations:</div>
                  <ul>{h.critique.alternative_explanations.map((w, i) => <li key={i}>{w}</li>)}</ul>
                </>
              )}
            </details>
          )}
        </div>
      ))}
    </>
  );
}
