import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getExperimentComparison, type ComparisonData } from "../api/client";

interface Props {
  experimentId: string;
}

export default function ComparisonView({ experimentId }: Props) {
  const [data, setData] = useState<{ name: string; before: number; during: number }[]>([]);

  useEffect(() => {
    getExperimentComparison(experimentId).then((comp: ComparisonData) => {
      const beforeMap = new Map(comp.before.map((b) => [b.name, b.avg_value]));
      const duringMap = new Map(comp.during.map((d) => [d.name, d.avg_value]));
      const allNames = new Set([...beforeMap.keys(), ...duringMap.keys()]);

      setData(
        [...allNames].map((name) => ({
          name,
          before: Math.round((beforeMap.get(name) ?? 0) * 100) / 100,
          during: Math.round((duringMap.get(name) ?? 0) * 100) / 100,
        }))
      );
    });
  }, [experimentId]);

  if (data.length === 0) return <p className="empty-state">No comparison data yet.</p>;

  return (
    <div className="chart-card">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis dataKey="name" fontSize={12} tick={{ fill: "var(--text-muted)" }} />
          <YAxis fontSize={12} tick={{ fill: "var(--text-muted)" }} />
          <Tooltip
            contentStyle={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "6px",
              color: "var(--text-primary)",
            }}
          />
          <Legend />
          <Bar dataKey="before" fill="var(--chart-secondary)" name="Before" radius={[4, 4, 0, 0]} />
          <Bar dataKey="during" fill="var(--accent)" name="During" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
