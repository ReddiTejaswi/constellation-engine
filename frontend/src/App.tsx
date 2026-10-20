import { useEffect, useMemo, useRef, useState } from "react";
import { Graph } from "./components/Graph";
import { Timeline } from "./components/Timeline";
import { EvidencePanel } from "./components/EvidencePanel";
import { HypothesisPanel } from "./components/HypothesisPanel";
import type { DiscoveryReport, Finding, Paper, StreamEvent } from "./types";

const STAGES = [
  "decomposition",
  "retrieval",
  "extraction",
  "graph",
  "connections",
  "contradictions",
  "gaps",
  "hypotheses",
  "critique",
  "report",
];

type Benchmark = { id: string; title: string; cutoff_year: number };

export default function App() {
  const [question, setQuestion] = useState(
    "What biological pathways could connect protein alpha-synuclein to neurodegeneration?"
  );
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState<Record<string, { status: string; message: string }>>({});
  const [report, setReport] = useState<DiscoveryReport | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [benchmarkId, setBenchmarkId] = useState<string>("");
  const [benchmarkMetrics, setBenchmarkMetrics] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => {});
    fetch("/api/benchmarks").then((r) => r.json()).then((d) => setBenchmarks(d.benchmarks || []));
  }, []);

  const findings = useMemo<Record<string, Finding>>(() => {
    const map: Record<string, Finding> = {};
    (report?.findings ?? []).forEach((f, i) => (map[`F${String(i).padStart(4, "0")}`] = f));
    return map;
  }, [report]);
  const papers = useMemo<Record<string, Paper>>(() => {
    const map: Record<string, Paper> = {};
    (report?.papers ?? []).forEach((p) => (map[p.identifier] = p));
    return map;
  }, [report]);

  async function run() {
    setRunning(true);
    setReport(null);
    setBenchmarkMetrics(null);
    setSelectedEdge(null);
    setStages({});
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const res = await fetch("/api/investigate/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error(await res.text());
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const c of chunks) {
          const line = c.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const ev: StreamEvent = JSON.parse(line.replace(/^data:\s*/, ""));
            setStages((s) => ({ ...s, [ev.stage]: { status: ev.status, message: ev.message } }));
            if (ev.stage === "report" && ev.status === "completed") {
              setReport(ev.data.report as DiscoveryReport);
            }
          } catch {
            // ignore malformed line
          }
        }
      }
    } catch (e: any) {
      setStages((s) => ({ ...s, error: { status: "error", message: String(e?.message || e) } }));
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  async function runBenchmark() {
    if (!benchmarkId) return;
    setRunning(true);
    setReport(null);
    setBenchmarkMetrics(null);
    setSelectedEdge(null);
    setStages({});
    try {
      const r = await fetch("/api/benchmark/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benchmark_id: benchmarkId }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "failed");
      setReport(d.report as DiscoveryReport);
      setBenchmarkMetrics(d.metrics);
      setQuestion(d.benchmark.question);
    } catch (e: any) {
      setStages((s) => ({ ...s, error: { status: "error", message: String(e?.message || e) } }));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">Scientific Discovery Engine</div>
        <div className="muted">
          {health?.model ? `model: ${health.model}` : "model: unconfigured"} · providers: {health?.providers_enabled?.join(", ") || "—"}
        </div>
      </header>

      <div style={{ display: "grid", gridTemplateRows: "auto auto auto 1fr auto", minHeight: 0 }}>
        <div className="question-bar">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Research question..."
            onKeyDown={(e) => { if (e.key === "Enter" && !running) run(); }}
          />
          <button className="primary" disabled={running} onClick={run}>
            {running ? "Investigating..." : "Investigate"}
          </button>
          <select value={benchmarkId} onChange={(e) => setBenchmarkId(e.target.value)}>
            <option value="">— historical benchmark —</option>
            {benchmarks.map((b) => (
              <option key={b.id} value={b.id}>
                {b.title} (≤ {b.cutoff_year})
              </option>
            ))}
          </select>
          <button disabled={running || !benchmarkId} onClick={runBenchmark}>
            Run benchmark
          </button>
        </div>

        <div className="progress">
          {STAGES.map((s) => {
            const st = stages[s];
            const cls = st?.status === "completed" ? "done" : st?.status === "error" ? "error" : st ? "active" : "";
            return (
              <div key={s} className={`step ${cls}`} title={st?.message || ""}>
                {s}{st ? ` · ${st.status}` : ""}
              </div>
            );
          })}
          {stages.error && <div className="step error">error · {stages.error.message}</div>}
        </div>

        {benchmarkMetrics && (
          <div className="panel">
            <h3>Benchmark metrics</h3>
            <div className="meta">
              entities recovered: <b>{benchmarkMetrics.entities_recovered}/{benchmarkMetrics.entities_total}</b> ·
              connections recovered: <b>{benchmarkMetrics.connections_multihop_recovered}/{benchmarkMetrics.connections_total}</b> ·
              best hypothesis similarity vs reference: <b>{benchmarkMetrics.best_hypothesis_similarity}</b>
            </div>
            <div className="meta" style={{ fontSize: 11, marginTop: 4 }}>{benchmarkMetrics.note}</div>
          </div>
        )}

        <div className="main" style={{ minHeight: 0 }}>
          <div style={{ display: "grid", gridTemplateRows: "60% 40%", minHeight: 0 }}>
            <div className="graph-wrap">
              {report ? (
                <Graph report={report} onSelectEdge={setSelectedEdge} selectedEdge={selectedEdge} />
              ) : (
                <div style={{ padding: 20, color: "var(--muted)" }}>
                  Enter a research question and the engine will decompose it, retrieve
                  evidence, extract findings, build a graph, and propose testable hypotheses.
                </div>
              )}
            </div>
            <div className="timeline-wrap panel">
              <h3>Discovery timeline</h3>
              {report ? <Timeline report={report} /> : <div className="meta">No evidence yet.</div>}
            </div>
          </div>

          <div className="evidence-panel">
            {report && (
              <>
                <div className="panel">
                  <h3>Key findings ({report.confidence_summary})</h3>
                  <ul>
                    {report.key_findings.slice(0, 10).map((k, i) => <li key={i}>{k}</li>)}
                  </ul>
                </div>
                <div className="panel">
                  <h3>Evidence / provenance</h3>
                  <EvidencePanel
                    report={report}
                    edgeId={selectedEdge}
                    findings={findings}
                    papers={papers}
                  />
                </div>
                <div className="panel">
                  <h3>Candidate hypotheses</h3>
                  <HypothesisPanel report={report} />
                </div>
                <div className="panel">
                  <h3>Cross-study connections ({report.connections.length})</h3>
                  {report.connections.slice(0, 10).map((c, i) => (
                    <div key={i} className="card">
                      <div><span className={`pill ${c.status}`}>{c.status}</span>{c.path_labels.join(" → ")}</div>
                      <div className="meta">{c.rationale}</div>
                    </div>
                  ))}
                </div>
                <div className="panel">
                  <h3>Research gaps ({report.gaps.length})</h3>
                  {report.gaps.slice(0, 10).map((g, i) => (
                    <div key={i} className="card">
                      <div>{g.description}</div>
                      <div className="meta">{g.rationale}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        <div className="disclaimer">
          {report?.disclaimer ??
            "These hypotheses are AI-generated research suggestions based on the retrieved literature. They are not experimentally validated scientific conclusions and require expert review and experimental testing."}
        </div>
      </div>
    </div>
  );
}
