type MetricCardProps = {
  label: string;
  value: string | number;
  hint: string;
  tone?: "teal" | "blue" | "amber" | "violet" | "rose" | "slate";
};

export function MetricCard({ label, value, hint, tone = "slate" }: MetricCardProps) {
  return (
    <article className={`metric-card tone-${tone}`}>
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
      <span className="metric-hint">{hint}</span>
    </article>
  );
}
