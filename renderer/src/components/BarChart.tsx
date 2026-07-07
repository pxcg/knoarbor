type BarChartProps = {
  data: Record<string, number>;
  limit?: number;
  emptyText?: string;
};

export function BarChart({ data, limit = 10, emptyText = "No data." }: BarChartProps) {
  const entries = Object.entries(data || {}).slice(0, limit);
  const max = Math.max(...entries.map(([, value]) => value), 1);
  if (!entries.length) {
    return <div className="empty-chart">{emptyText}</div>;
  }
  return (
    <div className="bar-chart">
      {entries.map(([label, value]) => (
        <div className="bar-row" key={label}>
          <span title={label}>{label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(value / max) * 100}%` }} />
          </div>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
