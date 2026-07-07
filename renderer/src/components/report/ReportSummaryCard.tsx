type ReportSummaryCardProps = {
  title: string;
  subtitle?: string;
  copy?: string;
};

export function ReportSummaryCard({ title, subtitle, copy }: ReportSummaryCardProps) {
  return (
    <div className="report-summary-card">
      <strong>{title}</strong>
      {subtitle && <span>{subtitle}</span>}
      {copy && <p>{copy}</p>}
    </div>
  );
}
