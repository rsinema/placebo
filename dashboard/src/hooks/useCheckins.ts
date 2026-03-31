import { useEffect, useState } from "react";
import { getResponses, type CheckinResponse } from "../api/client";

export function useCheckins(
  metricId: string | undefined,
  start?: string,
  end?: string
) {
  const [responses, setResponses] = useState<CheckinResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!metricId) return;
    setLoading(true);
    getResponses(metricId, start, end)
      .then(setResponses)
      .finally(() => setLoading(false));
  }, [metricId, start, end]);

  return { responses, loading };
}
