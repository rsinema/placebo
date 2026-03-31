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
