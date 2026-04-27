"use client";

interface Props {
  title: string;
  description: string;
  runnerPath: string;
  prepPath?: string;
}

/**
 * Placeholder shown for strategies that exist in the repo but don't
 * yet have backtest output JSON in `output/<strategy>/api/`.
 * Tells the user which scripts to run to generate the data that
 * would populate a full research dashboard.
 */
export default function ComingSoonPanel({
  title,
  description,
  runnerPath,
  prepPath,
}: Props) {
  return (
    <div className="panel">
      <div className="panel-head"><h2>{title}</h2></div>
      <div className="panel-body">
        <div style={{ maxWidth: 720, display: "flex", flexDirection: "column", gap: 18 }}>
          <p style={{ color: "var(--ink-2)", fontSize: 12, lineHeight: 1.6, margin: 0 }}>
            {description}
          </p>

          <div
            style={{
              border: "1px solid rgba(212,176,106,0.3)",
              background: "var(--gold-tint)",
              padding: "10px 14px",
              borderRadius: 2,
            }}
          >
            <div
              style={{
                fontSize: 9.5,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "var(--accent-2)",
                fontWeight: 600,
              }}
            >
              No backtest output yet
            </div>
            <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--ink-2)" }}>
              Run the backtest and data-prep scripts to populate this dashboard.
            </p>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div
                style={{
                  fontSize: 9.5,
                  letterSpacing: "0.18em",
                  textTransform: "uppercase",
                  color: "var(--ink-3)",
                  marginBottom: 4,
                }}
              >
                1. Run backtest
              </div>
              <code
                style={{
                  display: "block",
                  background: "var(--bg)",
                  border: "1px solid var(--rule)",
                  padding: "8px 12px",
                  fontSize: 12,
                  fontFamily: "var(--font-mono)",
                  color: "var(--accent-2)",
                  borderRadius: 2,
                }}
              >
                python {runnerPath}
              </code>
            </div>

            {prepPath && (
              <div>
                <div
                  style={{
                    fontSize: 9.5,
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    color: "var(--ink-3)",
                    marginBottom: 4,
                  }}
                >
                  2. Prepare frontend data
                </div>
                <code
                  style={{
                    display: "block",
                    background: "var(--bg)",
                    border: "1px solid var(--rule)",
                    padding: "8px 12px",
                    fontSize: 12,
                    fontFamily: "var(--font-mono)",
                    color: "var(--accent-2)",
                    borderRadius: 2,
                  }}
                >
                  python {prepPath}
                </code>
              </div>
            )}

            <p className="muted" style={{ marginTop: 4 }}>
              Once JSON lands in{" "}
              <code style={{ fontFamily: "var(--font-mono)", color: "var(--ink-2)" }}>
                output/&lt;strategy&gt;/api/
              </code>
              , wire the API base in{" "}
              <code style={{ fontFamily: "var(--font-mono)", color: "var(--ink-2)" }}>
                ResearchDashboard.tsx
              </code>{" "}
              and this placeholder will be replaced by the full dashboard.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
