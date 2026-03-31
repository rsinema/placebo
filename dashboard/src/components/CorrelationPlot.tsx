import { useEffect, useState } from "react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getCorrelation, type CorrelationPoint, type Metric } from "../api/client";

interface Props {
  metrics: Metric[];
}

export default function CorrelationPlot({ metrics }: Props) {
  const numericMetrics = metrics.filter((m) => m.response_type === "numeric");
  const [metricA, setMetricA] = useState("");
  const [metricB, setMetricB] = useState("");
  const [data, setData] = useState<CorrelationPoint[]>([]);

  useEffect(() => {
    if (!metricA || !metricB || metricA === metricB) {
      setData([]);
      return;
    }
    getCorrelation(metricA, metricB).then(setData);
  }, [metricA, metricB]);

  const nameA = numericMetrics.find((m) => m.id === metricA)?.name ?? "Metric A";
  const nameB = numericMetrics.find((m) => m.id === metricB)?.name ?? "Metric B";

  return (
    <div>
      <h3>Correlation</h3>
      <div className="correlation-selectors">
        <select value={metricA} onChange={(e) => setMetricA(e.target.value)}>
          <option value="">Select metric</option>
          {numericMetrics.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
        <span className="correlation-vs">vs</span>
        <select value={metricB} onChange={(e) => setMetricB(e.target.value)}>
          <option value="">Select metric</option>
          {numericMetrics.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
      </div>
      {data.length > 0 && (
        <div className="chart-card">
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="value_a" name={nameA} fontSize={12} type="number" domain={[0, 10]} tick={{ fill: "var(--text-muted)" }} />
              <YAxis dataKey="value_b" name={nameB} fontSize={12} type="number" domain={[0, 10]} tick={{ fill: "var(--text-muted)" }} />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                contentStyle={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: "6px",
                  color: "var(--text-primary)",
                }}
              />
              <Scatter data={data} fill="var(--accent)" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
      {metricA && metricB && metricA !== metricB && data.length === 0 && (
        <p className="empty-state">No overlapping data for these metrics yet.</p>
      )}
    </div>
  );
}
