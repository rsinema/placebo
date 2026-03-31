import { useState } from "react";
import { Link } from "react-router-dom";
import { format, subDays } from "date-fns";
import { useMetrics } from "../hooks/useMetrics";
import { useExperiments } from "../hooks/useExperiments";
import MetricChart from "../components/MetricChart";
import DateRangeFilter from "../components/DateRangeFilter";

export default function Dashboard() {
  const { metrics, loading } = useMetrics();
  const { experiments } = useExperiments();
  const [start, setStart] = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [end, setEnd] = useState(format(new Date(), "yyyy-MM-dd"));

  if (loading) return <p className="loading">Loading...</p>;

  const numericMetrics = metrics.filter((m) => m.response_type === "numeric");

  return (
    <div>
      <h2>Dashboard</h2>
      <DateRangeFilter start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      {numericMetrics.length === 0 && (
        <p className="empty-state">No numeric metrics yet. Add some via the Telegram bot!</p>
      )}
      {numericMetrics.map((m) => (
        <Link key={m.id} to={`/metrics/${m.id}`} style={{ textDecoration: "none", color: "inherit" }}>
          <MetricChart
            metricId={m.id}
            metricName={m.name}
            start={start}
            end={end}
            experiments={experiments}
            interactive
          />
        </Link>
      ))}
    </div>
  );
}
