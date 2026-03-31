import { useState } from "react";
import { format, parseISO } from "date-fns";
import { useExperiments } from "../hooks/useExperiments";
import { useMetrics } from "../hooks/useMetrics";
import ComparisonView from "../components/ComparisonView";
import CorrelationPlot from "../components/CorrelationPlot";

export default function Experiments() {
  const { experiments, loading } = useExperiments();
  const { metrics } = useMetrics();
  const [selected, setSelected] = useState<string | null>(null);

  if (loading) return <p className="loading">Loading...</p>;

  return (
    <div>
      <h2>Experiments</h2>
      {experiments.length === 0 && (
        <p className="empty-state">No experiments yet. Start one via the Telegram bot!</p>
      )}
      <div className="section">
        {experiments.map((exp) => {
          const isSelected = exp.id === selected;
          const status = exp.ended_at
            ? `ended ${format(parseISO(exp.ended_at), "MMM d, yyyy")}`
            : "ongoing";
          return (
            <div
              key={exp.id}
              onClick={() => setSelected(isSelected ? null : exp.id)}
              className={`card card-interactive ${isSelected ? "card-selected" : ""}`}
            >
              <strong>{exp.name}</strong>
              <span className="experiment-meta">
                {format(parseISO(exp.started_at), "MMM d, yyyy")} — {status}
              </span>
              {exp.hypothesis && (
                <div className="experiment-hypothesis">
                  {exp.hypothesis}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {selected && (
        <div className="section">
          <h3>Before vs During</h3>
          <ComparisonView experimentId={selected} />
        </div>
      )}

      <CorrelationPlot metrics={metrics} />
    </div>
  );
}
