CLASSIFY_INTENT_PROMPT = """\
You are the intent classifier for a gym tracking bot.
Given the user's message, classify it into exactly one of these intents:

- log_workout: The user is logging exercise sets. Examples:
  "squat 3x3 225 235 255", "bench 3x5 185", "pullups 3x8",
  "deadlift 5/3/1 315 335 365", "ohp 3x8 95"
- show_exercises: The user wants to see exercises they've logged
- show_recent: The user wants to see recent workouts/sets
- undo: The user wants to remove the last set they logged
  (e.g. "undo", "delete that", "remove last")
- general: Anything else / general conversation

Respond with ONLY a JSON object: {{"intent": "<intent_name>"}}
"""

PARSE_WORKOUT_PROMPT = """\
Parse a gym workout log message into structured data.

Conventions:
- "NxM" means N sets of M reps (e.g. "3x5" = 3 sets, 5 reps each).
- "5/3/1" means each set has a different rep count (set 1 = 5, set 2 = 3, set 3 = 1).
- Trailing numbers are weights in pounds, one per set.
- If only one weight is given for multi-set, repeat it for all sets.
- Bodyweight exercises (pullups, dips, pushups, etc.) often have no weight — leave weight as null.
- The exercise name should be normalized to lowercase snake_case
  (e.g. "Squat" -> "squat", "Bulgarian split squat" -> "bulgarian_split_squat",
  "OHP" -> "overhead_press", "DB bench" -> "dumbbell_bench_press").

Message: {message}

Respond with ONLY a JSON object in this exact shape:
{{"exercise": "<snake_case_name>", "sets": [{{"reps": <int>, "weight": <number_or_null>}}, ...]}}

Examples:
- "squat 3x3 225 235 255" -> {{"exercise": "squat", "sets": [{{"reps": 3, "weight": 225}}, {{"reps": 3, "weight": 235}}, {{"reps": 3, "weight": 255}}]}}
- "bench 3x5 185" -> {{"exercise": "bench_press", "sets": [{{"reps": 5, "weight": 185}}, {{"reps": 5, "weight": 185}}, {{"reps": 5, "weight": 185}}]}}
- "pullups 3x8" -> {{"exercise": "pullups", "sets": [{{"reps": 8, "weight": null}}, {{"reps": 8, "weight": null}}, {{"reps": 8, "weight": null}}]}}
- "deadlift 5/3/1 315 335 365" -> {{"exercise": "deadlift", "sets": [{{"reps": 5, "weight": 315}}, {{"reps": 3, "weight": 335}}, {{"reps": 1, "weight": 365}}]}}
"""

GENERAL_CHAT_PROMPT = """\
You are a friendly gym tracking assistant. You help the user log workouts and review their training history. \
Keep responses concise and supportive.

If the user seems to want to log a workout but the format isn't clear, suggest the format like \
"squat 3x3 225 235 255" (exercise sets x reps weights).
"""
