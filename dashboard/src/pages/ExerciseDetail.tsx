import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO, subDays } from "date-fns";
import {
  getExerciseSets,
  getExerciseStats,
  type ExerciseDailyStat,
  type ExerciseSet,
} from "../api/client";
import { useExercises } from "../hooks/useExercises";
import DateRangeFilter from "../components/DateRangeFilter";

interface ChartPoint {
  date: string;
  top_weight: number;
  est_1rm: number;
  set_count: number;
  is_pr: boolean;
}

function PRDot(props: any) {
  const { cx, cy, payload } = props;
  if (typeof cx !== "number" || typeof cy !== "number") return null;
  if (payload?.is_pr) {
    return (
      <g>
        <circle cx={cx} cy={cy} r={5} fill="var(--accent)" />
        <circle cx={cx} cy={cy} r={2} fill="var(--bg-card)" />
      </g>
    );
  }
  return <circle cx={cx} cy={cy} r={2.5} fill="var(--accent)" opacity={0.6} />;
}

export default function ExerciseDetail() {
  const { id } = useParams<{ id: string }>();
  const { exercises } = useExercises();
  const [start, setStart] = useState(format(subDays(new Date(), 90), "yyyy-MM-dd"));
  const [end, setEnd] = useState(format(new Date(), "yyyy-MM-dd"));
  const [stats, setStats] = useState<ExerciseDailyStat[]>([]);
  const [sets, setSets] = useState<ExerciseSet[]>([]);

  const exercise = exercises.find((e) => e.id === id);

  useEffect(() => {
    if (!id) return;
    getExerciseStats(id, start, end).then(setStats);
    getExerciseSets(id, start, end).then(setSets);
  }, [id, start, end]);

  const chartData: ChartPoint[] = useMemo(() => {
    let runningMax = 0;
    return stats.map((s) => {
      const isPR = s.est_1rm > runningMax;
      if (isPR) runningMax = s.est_1rm;
      return {
        date: format(parseISO(s.date), "MMM d"),
        top_weight: s.top_weight,
        est_1rm: Number(s.est_1rm.toFixed(1)),
        set_count: s.set_count,
        is_pr: isPR,
      };
    });
  }, [stats]);

  const sessionsByDate = useMemo(() => {
    const map = new Map<string, ExerciseSet[]>();
    for (const s of sets) {
      const day = format(parseISO(s.logged_at), "yyyy-MM-dd");
      if (!map.has(day)) map.set(day, []);
      map.get(day)!.push(s);
    }
    return Array.from(map.entries())
      .sort((a, b) => (a[0] < b[0] ? 1 : -1))
      .map(([day, daySets]) => ({
        day,
        sets: daySets.sort(
          (a, b) =>
            parseISO(a.logged_at).getTime() - parseISO(b.logged_at).getTime() ||
            a.set_number - b.set_number,
        ),
      }));
  }, [sets]);

  if (!exercise) return <p className="loading">Loading...</p>;

  const allTimeTop = stats.reduce((max, s) => Math.max(max, s.top_weight), 0);
  const allTime1RM = stats.reduce((max, s) => Math.max(max, s.est_1rm), 0);
  const totalSets = stats.reduce((sum, s) => sum + s.set_count, 0);
  const sessionCount = stats.length;
  const prCount = chartData.filter((p) => p.is_pr).length;

  return (
    <div>
      <div className="exercise-breadcrumb">
        <Link to="/workouts">← Workouts</Link>
      </div>
      <h2 className="exercise-title">{exercise.name.replace(/_/g, " ")}</h2>

      <DateRangeFilter
        start={start}
        end={end}
        onChange={(s, e) => {
          setStart(s);
          setEnd(e);
        }}
      />

      {chartData.length === 0 && (
        <div className="card empty-card">
          <p className="empty-state">No weighted sets in this date range.</p>
        </div>
      )}

      {chartData.length > 0 && (
        <>
          <div className="stats-row">
            <div className="stat-pill">
              <span className="stat-label">Top weight</span>
              <span className="stat-value">{allTimeTop}</span>
            </div>
            <div className="stat-pill">
              <span className="stat-label">Est 1RM</span>
              <span className="stat-value">{allTime1RM.toFixed(1)}</span>
            </div>
            <div className="stat-pill">
              <span className="stat-label">Sessions</span>
              <span className="stat-value">{sessionCount}</span>
            </div>
            <div className="stat-pill">
              <span className="stat-label">Sets</span>
              <span className="stat-value">{totalSets}</span>
            </div>
            {prCount > 0 && (
              <div className="stat-pill stat-pill-accent">
                <span className="stat-label">PRs</span>
                <span className="stat-value">{prCount}</span>
              </div>
            )}
          </div>

          <div className="chart-card">
            <div className="chart-title">Top set weight per day</div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="date" fontSize={12} tick={{ fill: "var(--text-muted)" }} />
                <YAxis fontSize={12} tick={{ fill: "var(--text-muted)" }} />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    color: "var(--text-primary)",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="top_weight"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  dot={{ r: 3, fill: "var(--accent)" }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card">
            <div className="chart-title">
              Estimated 1RM (Epley) <span className="chart-title-meta">— filled dot = PR</span>
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="date" fontSize={12} tick={{ fill: "var(--text-muted)" }} />
                <YAxis fontSize={12} tick={{ fill: "var(--text-muted)" }} />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    color: "var(--text-primary)",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="est_1rm"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  dot={<PRDot />}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card">
            <div className="chart-title">Sets per day</div>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="date" fontSize={12} tick={{ fill: "var(--text-muted)" }} />
                <YAxis
                  fontSize={12}
                  tick={{ fill: "var(--text-muted)" }}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    color: "var(--text-primary)",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="set_count"
                  stroke="var(--chart-secondary)"
                  strokeWidth={2}
                  dot={{ r: 3, fill: "var(--chart-secondary)" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      <div className="section" style={{ marginTop: "2rem" }}>
        <h3>Sessions</h3>
        {sessionsByDate.length === 0 && (
          <p className="empty-state">No sets in this date range.</p>
        )}
        {sessionsByDate.map(({ day, sets: daySets }) => {
          const dayDate = parseISO(day);
          const dayTopWeight = daySets.reduce(
            (max, s) => (s.weight !== null ? Math.max(max, s.weight) : max),
            0,
          );
          return (
            <div key={day} className="session-card session-card-compact">
              <div className="session-header">
                <span className="session-date">{format(dayDate, "EEE · MMM d, yyyy")}</span>
                <span className="session-meta">
                  {daySets.length} set{daySets.length !== 1 ? "s" : ""}
                  {dayTopWeight > 0 && <> · top {dayTopWeight}</>}
                </span>
              </div>
              <div className="session-set-pills">
                {daySets.map((s) => (
                  <span key={s.id} className="set-pill">
                    {s.weight === null ? `${s.reps}` : `${s.reps}@${s.weight}`}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
