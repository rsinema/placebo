import { useEffect, useState } from "react";
import { getExercises, type Exercise } from "../api/client";

export function useExercises() {
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getExercises()
      .then(setExercises)
      .finally(() => setLoading(false));
  }, []);

  return { exercises, loading };
}
