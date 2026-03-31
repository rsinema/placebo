interface Props {
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
}

export default function DateRangeFilter({ start, end, onChange }: Props) {
  return (
    <div className="date-filter">
      <label>
        From
        <input
          type="date"
          value={start}
          onChange={(e) => onChange(e.target.value, end)}
        />
      </label>
      <label>
        To
        <input
          type="date"
          value={end}
          onChange={(e) => onChange(start, e.target.value)}
        />
      </label>
    </div>
  );
}
