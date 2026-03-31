import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";
import { getResponses, type CheckinResponse, type Experiment } from "../api/client";

interface Props {
  metricId: string;
  metricName: string;
  start?: string;
  end?: string;
  experiments?: Experiment[];
  interactive?: boolean;
}

export default function MetricChart({ metricId, metricName, start, end, experiments = [], interactive = false }: Props) {
  const [data, setData] = useState<{ date: string; value: number }[]>([]);

  useEffect(() => {
    getResponses(metricId, start, end).then((responses: CheckinResponse[]) => {
      setData(
        responses.map((r) => ({
          date: format(parseISO(r.logged_at), "MM/dd"),
          value: parseFloat(r.response_value) || 0,
        }))
      );
    });
  }, [metricId, start, end]);

  return (
    <div className={`chart-card ${interactive ? "chart-card-interactive" : ""}`}>
      <div className="chart-title">{metricName}</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis dataKey="date" fontSize={12} tick={{ fill: "var(--text-muted)" }} />
          <YAxis fontSize={12} tick={{ fill: "var(--text-muted)" }} domain={[0, 10]} />
          <Tooltip
            contentStyle={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "6px",
              color: "var(--text-primary)",
            }}
          />
          <Line type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2} dot={false} />
          {experiments.map((exp) => (
            <ReferenceArea
              key={exp.id}
              x1={format(parseISO(exp.started_at), "MM/dd")}
              x2={exp.ended_at ? format(parseISO(exp.ended_at), "MM/dd") : undefined}
              fill="var(--accent)"
              fillOpacity={0.08}
              label={{ value: exp.name, fill: "var(--text-muted)", fontSize: 11 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
