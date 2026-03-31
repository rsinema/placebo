import { useEffect, useState } from "react";
import { getMetrics, type Metric } from "../api/client";

export function useMetrics() {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMetrics()
      .then(setMetrics)
      .finally(() => setLoading(false));
  }, []);

  return { metrics, loading };
}
