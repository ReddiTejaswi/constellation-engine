import type { DiscoveryReport } from "../types";

export function Timeline({ report }: { report: DiscoveryReport }) {
  const byYear = new Map<number, { title: string; id: string; url?: string | null }[]>();
  for (const p of report.papers) {
    const y = p.year ?? 0;
    if (!byYear.has(y)) byYear.set(y, []);
    byYear.get(y)!.push({ title: p.title, id: p.identifier, url: p.url });
  }
  const years = Array.from(byYear.keys())
    .filter((y) => y > 0)
    .sort((a, b) => a - b);

  if (years.length === 0) return <div className="muted">No dated sources.</div>;

  return (
    <div>
      {years.map((y) => (
        <div key={y} className="timeline-row">
          <div className="year">{y}</div>
          <div>
            {byYear.get(y)!.map((p) => (
              <div key={p.id} style={{ marginBottom: 4 }}>
                {p.url ? (
                  <a href={p.url} target="_blank" rel="noreferrer">
                    {p.title}
                  </a>
                ) : (
                  p.title
                )}{" "}
                <span className="badge">{p.id}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
      <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
        AI identifies connections across these findings and proposes testable hypotheses.
      </div>
    </div>
  );
}
