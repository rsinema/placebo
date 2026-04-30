import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { format, parseISO, isToday, isYesterday } from "date-fns";
import { useExercises } from "../hooks/useExercises";
import {
  getWorkoutCalendar,
  getWorkoutSessions,
  getWorkoutSummary,
  type CalendarDay,
  type WorkoutSession,
  type WorkoutSummary,
} from "../api/client";
import CalendarHeatmap from "../components/CalendarHeatmap";
import {
  inferMuscleGroup,
  MUSCLE_GROUP_ORDER,
  type MuscleGroup,
} from "../lib/exerciseGroups";

function prettyName(name: string): string {
  return name.replace(/_/g, " ");
}

function formatSet(reps: number, weight: number | null): string {
  if (weight === null) return `${reps}`;
  return `${reps}@${weight}`;
}

function relativeDate(iso: string): string {
  const d = parseISO(iso);
  if (isToday(d)) return "Today";
  if (isYesterday(d)) return "Yesterday";
  return format(d, "EEE · MMM d");
}

export default function Workouts() {
  const { exercises, loading } = useExercises();
  const [summary, setSummary] = useState<WorkoutSummary | null>(null);
  const [calendar, setCalendar] = useState<CalendarDay[]>([]);
  const [sessions, setSessions] = useState<WorkoutSession[]>([]);

  useEffect(() => {
    getWorkoutSummary(7).then(setSummary);
    getWorkoutCalendar(84).then(setCalendar);
    getWorkoutSessions(8).then(setSessions);
  }, []);

  const grouped = useMemo(() => {
    const buckets: Record<MuscleGroup, typeof exercises> = {
      Push: [],
      Pull: [],
      Legs: [],
      Core: [],
      Other: [],
    };
    for (const e of exercises) {
      buckets[inferMuscleGroup(e.name)].push(e);
    }
    for (const k of MUSCLE_GROUP_ORDER) {
      buckets[k].sort((a, b) => b.set_count - a.set_count);
    }
    return buckets;
  }, [exercises]);

  if (loading) return <p className="loading">Loading...</p>;

  const hasData = exercises.length > 0;

  return (
    <div>
      <div className="page-heading">
        <h2>Workouts</h2>
        {summary && summary.session_count > 0 && (
          <span className="page-heading-meta">
            {summary.session_count} session{summary.session_count !== 1 ? "s" : ""} this week
          </span>
        )}
      </div>

      {!hasData && (
        <div className="card empty-card">
          <p className="empty-state">
            No workouts yet. Send something like <code>squat 3x5 225</code> to the gym bot to get started.
          </p>
        </div>
      )}

      {hasData && summary && (
        <div className="hero-card">
          <div className="hero-stats">
            <div className="hero-stat">
              <span className="hero-stat-value">{summary.session_count}</span>
              <span className="hero-stat-label">sessions</span>
            </div>
            <div className="hero-stat">
              <span className="hero-stat-value">{summary.lift_count}</span>
              <span className="hero-stat-label">lifts</span>
            </div>
            <div className="hero-stat">
              <span className="hero-stat-value">{summary.set_count}</span>
              <span className="hero-stat-label">sets</span>
            </div>
            <div className="hero-stat-divider" />
            <div className="hero-stat-period">last 7 days</div>
          </div>

          {summary.top_exercises.length > 0 && (
            <div className="hero-top-list">
              <div className="hero-section-label">Top this week</div>
              {summary.top_exercises.slice(0, 3).map((ex) => (
                <Link
                  key={ex.id}
                  to={`/exercises/${ex.id}`}
                  className="hero-top-row"
                >
                  <span className="hero-top-name">{prettyName(ex.name)}</span>
                  <span className="hero-top-meta">
                    {ex.top_weight !== null && <span>top {ex.top_weight}</span>}
                    <span className="muted">·</span>
                    <span>{ex.set_count} sets</span>
                    <span className="muted">·</span>
                    <span>
                      {ex.lift_count} lift{ex.lift_count !== 1 ? "s" : ""}
                    </span>
                  </span>
                </Link>
              ))}
            </div>
          )}

          <div className="hero-heatmap">
            <div className="hero-section-label">Last 12 weeks</div>
            <CalendarHeatmap data={calendar} weeks={12} />
          </div>
        </div>
      )}

      {hasData && (
        <div className="section">
          <h3>Exercises</h3>
          {MUSCLE_GROUP_ORDER.map((group) => {
            const items = grouped[group];
            if (items.length === 0) return null;
            return (
              <div key={group} className="muscle-group">
                <div className="muscle-group-label">{group}</div>
                <div className="exercise-grid">
                  {items.map((e) => (
                    <Link
                      key={e.id}
                      to={`/exercises/${e.id}`}
                      className="exercise-tile"
                    >
                      <span className="exercise-tile-name">{prettyName(e.name)}</span>
                      <span className="exercise-tile-meta">
                        {e.set_count} sets
                        {e.last_logged_at && (
                          <>
                            {" · "}
                            {format(parseISO(e.last_logged_at), "MMM d")}
                          </>
                        )}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {sessions.length > 0 && (
        <div className="section">
          <h3>Recent sessions</h3>
          {sessions.map((s) => (
            <div key={s.date} className="session-card">
              <div className="session-header">
                <span className="session-date">{relativeDate(s.started_at)}</span>
                <span className="session-meta">
                  {s.exercises.length} lift{s.exercises.length !== 1 ? "s" : ""} ·{" "}
                  {s.set_count} sets
                </span>
              </div>
              <div className="session-exercises">
                {s.exercises.map((ex) => (
                  <Link
                    key={ex.log_group_id}
                    to={`/exercises/${ex.exercise_id}`}
                    className="session-exercise-row"
                  >
                    <span className="session-exercise-name">
                      {prettyName(ex.exercise_name)}
                    </span>
                    <span className="session-exercise-sets">
                      {ex.sets.map((set, i) => (
                        <span key={i} className="set-pill">
                          {formatSet(set.reps, set.weight)}
                        </span>
                      ))}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
