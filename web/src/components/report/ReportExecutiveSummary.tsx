import { localizeReportValue } from "../reportLabels";

export function ReportExecutiveSummary({
  changedPages,
  failures,
  metrics,
  t,
  writtenPages,
}: {
  changedPages: number;
  failures: number;
  metrics: Array<{ key: string; value: string }>;
  t: (key: string) => string;
  writtenPages: number;
}) {
  const metricMap = new Map(metrics.map((metric) => [normalizeMetricKey(metric.key), metric.value]));
  const appliedOperations = pickMetric(metricMap, ["appliedoperations", "applied_operations"]);
  const totalTokens = pickMetric(metricMap, ["totaltokens", "total_tokens"]);
  const elapsed = pickMetric(metricMap, ["elapsedseconds", "elapsed_seconds", "durationseconds", "duration_seconds"]);
  const status = failures > 0 ? t("reportNeedsAttention") : changedPages || writtenPages || appliedOperations ? t("reportCompletedWithChanges") : t("reportNoActionNeeded");
  const cards = [
    { label: t("reportOutcome"), value: status },
    { label: t("reportWrittenPages"), value: String(writtenPages) },
    { label: t("reportChangedPages"), value: String(changedPages) },
    { label: t("reportFailures"), value: String(failures), danger: failures > 0 },
    totalTokens ? { label: t("totalTokens"), value: localizeReportValue(totalTokens, t) } : null,
    elapsed ? { label: t("elapsed"), value: `${localizeReportValue(elapsed, t)}s` } : null,
  ].filter((item): item is { label: string; value: string; danger?: boolean } => Boolean(item));
  return (
    <section className="report-executive-summary">
      <h3>{t("reportExecutiveSummary")}</h3>
      <dl>
        {cards.map((card) => (
          <div className={card.danger ? "danger" : ""} key={card.label}>
            <dt>{card.label}</dt>
            <dd>{card.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function normalizeMetricKey(key: string) {
  return key.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function pickMetric(metrics: Map<string, string>, keys: string[]) {
  for (const key of keys) {
    const value = metrics.get(normalizeMetricKey(key));
    if (value && value !== "n/a" && value !== "N/A") return value;
  }
  return null;
}
