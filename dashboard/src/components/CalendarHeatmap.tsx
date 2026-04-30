import { format, startOfWeek, addDays, subDays, isSameDay } from "date-fns";
import type { CalendarDay } from "../api/client";

interface Props {
  data: CalendarDay[];
  weeks?: number;
}

const DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];

function intensityTier(setCount: number): 0 | 1 | 2 | 3 | 4 {
  if (setCount <= 0) return 0;
  if (setCount <= 4) return 1;
  if (setCount <= 9) return 2;
  if (setCount <= 15) return 3;
  return 4;
}

export default function CalendarHeatmap({ data, weeks = 12 }: Props) {
  const today = new Date();
  // Anchor the rightmost column on the week containing today (Sunday-start).
  const lastWeekStart = startOfWeek(today, { weekStartsOn: 0 });
  const firstWeekStart = subDays(lastWeekStart, (weeks - 1) * 7);

  const byDate = new Map<string, CalendarDay>();
  for (const d of data) byDate.set(d.date, d);

  const columns: { date: Date; entry: CalendarDay | undefined; isFuture: boolean }[][] = [];
  for (let w = 0; w < weeks; w++) {
    const colStart = addDays(firstWeekStart, w * 7);
    const col: { date: Date; entry: CalendarDay | undefined; isFuture: boolean }[] = [];
    for (let d = 0; d < 7; d++) {
      const date = addDays(colStart, d);
      const iso = format(date, "yyyy-MM-dd");
      const isFuture = date > today && !isSameDay(date, today);
      col.push({ date, entry: byDate.get(iso), isFuture });
    }
    columns.push(col);
  }

  const maxSets = Math.max(0, ...data.map((d) => d.set_count));

  return (
    <div className="heatmap">
      <div className="heatmap-day-labels">
        {DAY_LABELS.map((label, i) => (
          <div key={i} className="heatmap-day-label">
            {label}
          </div>
        ))}
      </div>
      <div className="heatmap-grid">
        {columns.map((col, ci) => (
          <div key={ci} className="heatmap-col">
            {col.map(({ date, entry, isFuture }, di) => {
              const tier = entry ? intensityTier(entry.set_count) : 0;
              const title = entry
                ? `${format(date, "MMM d")} — ${entry.set_count} sets, ${Math.round(
                    entry.volume
                  )} lb volume`
                : `${format(date, "MMM d")} — rest`;
              return (
                <div
                  key={di}
                  className={`heatmap-cell tier-${tier} ${isFuture ? "future" : ""}`}
                  title={title}
                />
              );
            })}
          </div>
        ))}
      </div>
      <div className="heatmap-legend">
        <span className="heatmap-legend-label">Less</span>
        {[0, 1, 2, 3, 4].map((t) => (
          <div key={t} className={`heatmap-cell tier-${t}`} />
        ))}
        <span className="heatmap-legend-label">More</span>
        {maxSets > 0 && (
          <span className="heatmap-legend-label muted">· max {maxSets} sets/day</span>
        )}
      </div>
    </div>
  );
}

