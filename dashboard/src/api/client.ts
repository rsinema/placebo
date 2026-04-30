const BASE = "/api";

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export interface Metric {
  id: string;
  name: string;
  question_prompt: string;
  response_type: "numeric" | "boolean" | "text";
  active: boolean;
  created_at: string;
  archived_at: string | null;
}

export interface CheckinResponse {
  id: string;
  metric_id: string;
  response_value: string;
  notes: string | null;
  logged_at: string;
  metric_name?: string;
}

export interface Experiment {
  id: string;
  name: string;
  hypothesis: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface MetricStats {
  count: number;
  avg: number | null;
  min: number | null;
  max: number | null;
}

export interface CorrelationPoint {
  date: string;
  value_a: number;
  value_b: number;
}

export interface ComparisonData {
  experiment: Experiment;
  before: { id: string; name: string; avg_value: number }[];
  during: { id: string; name: string; avg_value: number }[];
}

export function getMetrics(includeArchived = false): Promise<Metric[]> {
  return fetchJSON(`/metrics?include_archived=${includeArchived}`);
}

export function getResponses(
  metricId: string,
  start?: string,
  end?: string
): Promise<CheckinResponse[]> {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const qs = params.toString();
  return fetchJSON(`/metrics/${metricId}/responses${qs ? `?${qs}` : ""}`);
}

export function getMetricStats(
  metricId: string,
  start?: string,
  end?: string
): Promise<MetricStats> {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const qs = params.toString();
  return fetchJSON(`/metrics/${metricId}/stats${qs ? `?${qs}` : ""}`);
}

export function getCorrelation(
  metricA: string,
  metricB: string,
  start?: string,
  end?: string
): Promise<CorrelationPoint[]> {
  const params = new URLSearchParams({ metric_a: metricA, metric_b: metricB });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  return fetchJSON(`/metrics/correlation?${params}`);
}

export function getExperiments(): Promise<Experiment[]> {
  return fetchJSON("/experiments");
}

export function getExperimentComparison(id: string): Promise<ComparisonData> {
  return fetchJSON(`/experiments/${id}/comparison`);
}

export function getLatestCheckin(): Promise<CheckinResponse[]> {
  return fetchJSON("/checkins/latest");
}

// ── Gym ──────────────────────────────────────────────────────────────────

export interface Exercise {
  id: string;
  name: string;
  category: string | null;
  created_at: string;
  set_count: number;
  last_logged_at: string | null;
}

export interface ExerciseSet {
  id: string;
  exercise_id: string;
  set_number: number;
  reps: number;
  weight: number | null;
  rpe: number | null;
  notes: string | null;
  log_group_id: string;
  logged_at: string;
}

export interface ExerciseDailyStat {
  date: string;
  top_weight: number;
  volume: number;
  est_1rm: number;
  set_count: number;
}

export interface RecentWorkoutSet {
  id: string;
  set_number: number;
  reps: number;
  weight: number | null;
  rpe: number | null;
  notes: string | null;
}

export interface RecentWorkout {
  log_group_id: string;
  exercise_id: string;
  exercise_name: string;
  logged_at: string;
  sets: RecentWorkoutSet[];
}

export function getExercises(): Promise<Exercise[]> {
  return fetchJSON("/exercises");
}

export function getExerciseSets(
  exerciseId: string,
  start?: string,
  end?: string
): Promise<ExerciseSet[]> {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const qs = params.toString();
  return fetchJSON(`/exercises/${exerciseId}/sets${qs ? `?${qs}` : ""}`);
}

export function getExerciseStats(
  exerciseId: string,
  start?: string,
  end?: string
): Promise<ExerciseDailyStat[]> {
  const params = new URLSearchParams();
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const qs = params.toString();
  return fetchJSON(`/exercises/${exerciseId}/stats${qs ? `?${qs}` : ""}`);
}

export function getRecentWorkouts(limit = 20): Promise<RecentWorkout[]> {
  return fetchJSON(`/workouts/recent?limit=${limit}`);
}

export interface WorkoutSummary {
  days: number;
  set_count: number;
  lift_count: number;
  session_count: number;
  top_exercises: {
    id: string;
    name: string;
    top_weight: number | null;
    lift_count: number;
    set_count: number;
  }[];
}

export interface CalendarDay {
  date: string;
  set_count: number;
  volume: number;
}

export interface SessionExercise {
  log_group_id: string;
  exercise_id: string;
  exercise_name: string;
  sets: { set_number: number; reps: number; weight: number | null }[];
}

export interface WorkoutSession {
  date: string;
  started_at: string;
  set_count: number;
  volume: number;
  exercises: SessionExercise[];
}

export function getWorkoutSummary(days = 7): Promise<WorkoutSummary> {
  return fetchJSON(`/workouts/summary?days=${days}`);
}

export function getWorkoutCalendar(days = 84): Promise<CalendarDay[]> {
  return fetchJSON(`/workouts/calendar?days=${days}`);
}

export function getWorkoutSessions(limit = 10): Promise<WorkoutSession[]> {
  return fetchJSON(`/workouts/sessions?limit=${limit}`);
}
