import { useEffect, useMemo, useState } from "react";

import { getTokenAnalysis, type TokenAnalysis, type TokenCallRecord, type TokenMetricGroup, type TokenPayloadFieldGroup } from "../api/client";
import { BarChart } from "../components/BarChart";
import { LoadingBlock } from "../components/LoadingBlock";
import { MetricCard } from "../components/MetricCard";
import type { AppContext } from "../appContext";

type Props = {
  context: AppContext;
};

const LEDGER_LIMITS = [500, 1000, 5000, 10000];

export function TokensPage({ context }: Props) {
  const [analysis, setAnalysis] = useState<TokenAnalysis | null>(null);
  const [limit, setLimit] = useState(5000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getTokenAnalysis(context.vaultPath, limit)
      .then((result) => {
        if (!cancelled) setAnalysis(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [context.vaultPath, limit]);

  const flowAgentGroups = useMemo(() => buildFlowAgentGroups(analysis?.top_calls || [], analysis?.by_flow || []), [analysis]);
  const expensiveRun = analysis?.recent_runs?.[0];
  const topCall = analysis?.top_calls?.[0];

  if (loading && !analysis) {
    return <section className="panel"><LoadingBlock title={context.t("tokensLoading")} copy={context.t("tokensLoadingCopy")} /></section>;
  }

  if (error) {
    return <section className="panel"><p className="panel-copy">{error}</p></section>;
  }

  if (!analysis || analysis.record_count === 0) {
    return (
      <section className="panel">
        <div className="section-heading">
          <h2>{context.t("tokensTitle")}</h2>
          <p>{context.t("tokenNoData")}</p>
        </div>
      </section>
    );
  }

  const totals = analysis.totals;
  return (
    <div className="page-stack token-page">
      <section className="panel token-header">
        <div className="section-heading">
          <h2>{context.t("tokenCostOverview")}</h2>
          <p>{context.t("tokenCostOverviewCopy")}</p>
        </div>
        <label className="token-range-select">
          <span>{context.t("tokenAnalysisRange")}</span>
          <select value={limit} onChange={(event) => setLimit(Number(event.target.value))}>
            {LEDGER_LIMITS.map((value) => (
              <option key={value} value={value}>
                {context.t("tokenLatestRecords").replace("{count}", formatNumber(value))}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="metric-grid">
        <MetricCard label={context.t("tokenMetricTotal")} value={formatNumber(totals.total_tokens)} hint={`${context.t("tokenMetricCalls")}: ${formatNumber(totals.call_count)}`} tone="blue" />
        <MetricCard label={context.t("tokenMetricCacheRate")} value={formatPercent(totals.prompt_cache_rate)} hint={`${context.t("tokenMetricCached")}: ${formatNumber(totals.prompt_cached_tokens)}`} tone="violet" />
        <MetricCard label={context.t("tokenLatestRun")} value={formatNumber(expensiveRun?.total_tokens)} hint={expensiveRun?.run_id || context.t("unknown")} tone="teal" />
        <MetricCard label={context.t("tokenMostExpensiveCall")} value={formatNumber(topCall?.total_tokens)} hint={topCall ? `${agentLabel(topCall.agent, context.t)} · ${flowLabel(topCall.flow || "unknown", context.t)}` : context.t("unknown")} tone="amber" />
      </section>

      <section className="panel token-flow-panel">
        <div className="section-heading">
          <h2>{context.t("tokenFlowBreakdown")}</h2>
          <p>{context.t("tokenFlowBreakdownCopy")}</p>
        </div>
        <div className="token-flow-list">
          {flowAgentGroups.map((flow) => (
            <article className="token-flow-card" key={flow.name}>
              <div className="token-flow-header">
                <div>
                  <h3>{flowLabel(flow.name, context.t)}</h3>
                  <p>{`${context.t("tokenMetricTotal")}: ${formatNumber(flow.total.total_tokens)} · ${context.t("tokenMetricCalls")}: ${formatNumber(flow.total.call_count)}`}</p>
                </div>
                <span className="token-cache-pill">{`${context.t("tokenMetricCacheRate")}: ${formatPercent(flow.total.prompt_cache_rate)}`}</span>
              </div>
              <TokenTable context={context} rows={flow.agents} nameFormatter={(value) => agentLabel(value, context.t)} compact />
            </article>
          ))}
          {!flowAgentGroups.length && <p className="panel-copy">{context.t("tokenNoData")}</p>}
        </div>
      </section>

      <section className="two-column-grid">
        <article className="panel">
          <div className="section-heading">
            <h2>{context.t("tokenOptimizationDiagnosis")}</h2>
            <p>{context.t("tokenOptimizationDiagnosisCopy")}</p>
          </div>
          <div className="token-diagnosis-list">
            <DiagnosisItem label={context.t("tokenMostExpensiveSource")} value={analysis.by_source?.[0]?.name} metric={formatNumber(analysis.by_source?.[0]?.total_tokens)} />
            <DiagnosisItem label={context.t("tokenMostExpensivePage")} value={analysis.by_page?.[0]?.name} metric={formatNumber(analysis.by_page?.[0]?.total_tokens)} />
            <DiagnosisItem label={context.t("tokenLargestPayloadField")} value={analysis.by_payload_field?.[0]?.name} metric={formatNumber(analysis.by_payload_field?.[0]?.payload_chars)} />
          </div>
        </article>
        <article className="panel">
          <div className="section-heading">
            <h2>{context.t("tokenPayloadDiagnosis")}</h2>
            <p>{context.t("tokenPayloadDiagnosisCopy")}</p>
          </div>
          <BarChart data={toPayloadBarData(analysis.by_payload_field || [])} limit={8} emptyText={context.t("tokenNoData")} />
        </article>
      </section>

      <details className="panel token-detail-panel">
        <summary>{context.t("tokenAdvancedDetails")}</summary>
        <div className="token-detail-grid">
          <PayloadFieldTable context={context} rows={analysis.by_payload_field || []} />
          <TokenTable context={context} title={context.t("tokenRecentRuns")} rows={analysis.recent_runs} compact />
          <article className="panel">
            <div className="section-heading">
              <h2>{context.t("tokenTopCalls")}</h2>
            </div>
            <TopCallsTable context={context} rows={analysis.top_calls} />
          </article>
        </div>
      </details>
    </div>
  );
}

type TokenMetricRow = Partial<TokenMetricGroup> & { run_id?: string };

function TokenTable({
  context,
  title,
  rows,
  compact = false,
  nameFormatter,
}: {
  context: AppContext;
  title?: string;
  rows: TokenMetricRow[];
  compact?: boolean;
  nameFormatter?: (value: string) => string;
}) {
  return (
    <article className="panel">
      {title && (
        <div className="section-heading">
          <h2>{title}</h2>
        </div>
      )}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{context.t("name")}</th>
              <th>{context.t("tokenMetricCalls")}</th>
              <th>{context.t("tokenMetricTotal")}</th>
              {!compact && <th>{context.t("tokenMetricPrompt")}</th>}
              {!compact && <th>{context.t("tokenMetricCompletion")}</th>}
              <th>{context.t("tokenMetricCacheRate")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const name = String(row.name || row.run_id || "unknown");
              return (
                <tr key={name}>
                  <td title={name}>{nameFormatter ? nameFormatter(name) : name}</td>
                  <td>{formatNumber(row.call_count)}</td>
                  <td>{formatNumber(row.total_tokens)}</td>
                  {!compact && <td>{formatNumber(row.prompt_tokens)}</td>}
                  {!compact && <td>{formatNumber(row.completion_tokens)}</td>}
                  <td>{formatPercent(row.prompt_cache_rate)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function TopCallsTable({ context, rows }: { context: AppContext; rows: TokenCallRecord[] }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>{context.t("flow")}</th>
            <th>Agent</th>
            <th>{context.t("source")}</th>
            <th>{context.t("tokenTopField")}</th>
            <th>{context.t("tokenMetricTotal")}</th>
            <th>{context.t("tokenMetricCacheRate")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.run_id}-${row.agent}-${index}`}>
              <td>{flowLabel(row.flow || "unknown", context.t)}</td>
              <td>{agentLabel(row.agent, context.t)}</td>
              <td title={row.source_file || ""}>{shortPath(row.source_file || row.page_paths?.[0] || "unknown")}</td>
              <td>{row.payload_top_field || "n/a"}</td>
              <td>{formatNumber(row.total_tokens)}</td>
              <td>{formatPercent(row.prompt_cache_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PayloadFieldTable({ context, rows }: { context: AppContext; rows: TokenPayloadFieldGroup[] }) {
  return (
    <article className="panel">
      <div className="section-heading">
        <h2>{context.t("tokenPayloadFields")}</h2>
        <p>{context.t("tokenPayloadFieldsCopy")}</p>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>{context.t("tokenField")}</th>
              <th>{context.t("tokenMetricCalls")}</th>
              <th>{context.t("tokenChars")}</th>
              <th>{context.t("tokenTopInCalls")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td title={row.name}>{row.name}</td>
                <td>{formatNumber(row.call_count)}</td>
                <td>{formatNumber(row.payload_chars)}</td>
                <td>{formatNumber(row.top_call_count)}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={4}>{context.t("tokenNoPayloadRecords")}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function DiagnosisItem({ label, value, metric }: { label: string; value?: string; metric: string }) {
  return (
    <div className="token-diagnosis-item">
      <span>{label}</span>
      <strong title={value || "n/a"}>{value ? shortPath(value) : "n/a"}</strong>
      <em>{metric}</em>
    </div>
  );
}

type FlowAgentGroup = {
  name: string;
  total: TokenMetricGroup;
  agents: TokenMetricGroup[];
};

function buildFlowAgentGroups(calls: TokenCallRecord[], byFlow: TokenMetricGroup[]): FlowAgentGroup[] {
  const flows = new Map<string, Map<string, TokenMetricGroup>>();
  for (const call of calls) {
    const flow = call.flow || "unknown";
    const agent = call.agent || "unknown";
    if (!flows.has(flow)) flows.set(flow, new Map());
    const agents = flows.get(flow)!;
    const existing = agents.get(agent) || emptyMetric(agent);
    agents.set(agent, mergeMetric(existing, call));
  }
  for (const flow of byFlow) {
    if (!flows.has(flow.name)) flows.set(flow.name, new Map());
  }
  const preferredOrder = ["ingest", "lint", "query", "chat", "unknown"];
  return [...flows.entries()]
    .sort(([left], [right]) => preferredOrderIndex(left, preferredOrder) - preferredOrderIndex(right, preferredOrder))
    .map(([name, agents]) => {
      const rows = [...agents.values()].sort((left, right) => (right.total_tokens || 0) - (left.total_tokens || 0));
      const total = byFlow.find((item) => item.name === name) || rows.reduce((acc, row) => mergeMetric(acc, row), emptyMetric(name));
      return { name, agents: rows, total };
    });
}

function emptyMetric(name: string): TokenMetricGroup {
  return {
    name,
    call_count: 0,
    prompt_tokens: 0,
    prompt_cached_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
    elapsed_seconds: 0,
    tokens_per_second: null,
  };
}

function mergeMetric<T extends Partial<TokenMetricGroup>>(base: TokenMetricGroup, item: T): TokenMetricGroup {
  const promptTokens = base.prompt_tokens + numberValue(item.prompt_tokens);
  const cachedTokens = base.prompt_cached_tokens + numberValue(item.prompt_cached_tokens);
  const completionTokens = base.completion_tokens + numberValue(item.completion_tokens);
  const elapsedSeconds = base.elapsed_seconds + numberValue(item.elapsed_seconds);
  return {
    ...base,
    call_count: base.call_count + numberValue(item.call_count || 1),
    prompt_tokens: promptTokens,
    prompt_cached_tokens: cachedTokens,
    completion_tokens: completionTokens,
    total_tokens: base.total_tokens + numberValue(item.total_tokens),
    elapsed_seconds: elapsedSeconds,
    tokens_per_second: elapsedSeconds > 0 ? completionTokens / elapsedSeconds : null,
    prompt_cache_rate: promptTokens > 0 ? cachedTokens / promptTokens : null,
  };
}

function preferredOrderIndex(value: string, order: string[]): number {
  const index = order.indexOf(value);
  return index >= 0 ? index : order.length;
}

function flowLabel(flow: string, t: (key: string) => string): string {
  const key = `flow.${flow}`;
  const translated = t(key);
  return translated === key ? flow : translated;
}

function agentLabel(agent: string | undefined, t: (key: string) => string): string {
  const value = agent || "unknown";
  const key = `agent.${value}`;
  const translated = t(key);
  return translated === key ? value : translated;
}

function toPayloadBarData(rows: TokenPayloadFieldGroup[]): Record<string, number> {
  return Object.fromEntries(rows.slice(0, 8).map((row) => [row.name, row.payload_chars]));
}

function shortPath(value: string): string {
  const normalized = value.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length <= 2) return normalized;
  return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`;
}

function formatNumber(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? Math.round(value).toLocaleString() : "n/a";
}

function formatPercent(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "n/a";
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
