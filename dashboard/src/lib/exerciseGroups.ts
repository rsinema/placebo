export type MuscleGroup = "Push" | "Pull" | "Legs" | "Core" | "Other";

const PATTERNS: { group: MuscleGroup; matches: RegExp[] }[] = [
  {
    group: "Push",
    matches: [
      /bench/i,
      /press/i,
      /\bohp\b/i,
      /overhead/i,
      /dip/i,
      /push.?up/i,
      /tricep/i,
      /skull.?crusher/i,
      /pec.?fly/i,
      /chest/i,
      /shoulder/i,
      /lateral.?raise/i,
    ],
  },
  {
    group: "Pull",
    matches: [
      /pull.?up/i,
      /chin.?up/i,
      /\brow\b/i,
      /lat.?pulldown/i,
      /pulldown/i,
      /curl/i,
      /shrug/i,
      /face.?pull/i,
      /deadlift/i,
      /rdl/i,
    ],
  },
  {
    group: "Legs",
    matches: [
      /squat/i,
      /lunge/i,
      /leg.?press/i,
      /leg.?ext/i,
      /leg.?curl/i,
      /hip.?thrust/i,
      /glute/i,
      /calf/i,
      /step.?up/i,
      /\bquad\b/i,
      /hamstring/i,
    ],
  },
  {
    group: "Core",
    matches: [
      /plank/i,
      /crunch/i,
      /sit.?up/i,
      /leg.?raise/i,
      /\bab\b/i,
      /hollow/i,
      /russian.?twist/i,
    ],
  },
];

export function inferMuscleGroup(exerciseName: string): MuscleGroup {
  // Deadlift is debatable; landed in Pull above. Check Legs override only if explicitly leg-related.
  for (const { group, matches } of PATTERNS) {
    if (matches.some((re) => re.test(exerciseName))) return group;
  }
  return "Other";
}

export const MUSCLE_GROUP_ORDER: MuscleGroup[] = ["Push", "Pull", "Legs", "Core", "Other"];
