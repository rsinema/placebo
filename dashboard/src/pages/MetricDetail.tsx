import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { format, subDays } from "date-fns";
import { getMetricStats, type MetricStats } from "../api/client";
import { useMetrics } from "../hooks/useMetrics";
import { useExperiments } from "../hooks/useExperiments";
import MetricChart from "../components/MetricChart";
import DateRangeFilter from "../components/DateRangeFilter";

export default function MetricDetail() {
  const { id } = useParams<{ id: string }>();
  const { metrics } = useMetrics();
  const { experiments } = useExperiments();
  const [start, setStart] = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [end, setEnd] = useState(format(new Date(), "yyyy-MM-dd"));
  const [stats, setStats] = useState<MetricStats | null>(null);

  const metric = metrics.find((m) => m.id === id);

  useEffect(() => {
    if (!id) return;
    getMetricStats(id, start, end).then(setStats);
  }, [id, start, end]);

  if (!metric) return <p className="loading">Loading...</p>;

  return (
    <div>
      <h2>{metric.name}</h2>
      <p className="metric-prompt">{metric.question_prompt}</p>
      <DateRangeFilter start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />

      <MetricChart
        metricId={metric.id}
        metricName={metric.name}
        start={start}
        end={end}
        experiments={experiments}
      />

      {stats && stats.count > 0 && (
        <div className="stats-row">
          <div className="stat-pill">
            <span className="stat-label">Avg</span>
            <span className="stat-value">{stats.avg?.toFixed(1)}</span>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Min</span>
            <span className="stat-value">{stats.min}</span>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Max</span>
            <span className="stat-value">{stats.max}</span>
          </div>
          <div className="stat-pill">
            <span className="stat-label">Count</span>
            <span className="stat-value">{stats.count}</span>
          </div>
        </div>
      )}
    </div>
  );
}
