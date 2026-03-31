import { useEffect, useState } from "react";
import { getExperiments, type Experiment } from "../api/client";

export function useExperiments() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getExperiments()
      .then(setExperiments)
      .finally(() => setLoading(false));
  }, []);

  return { experiments, loading };
}
