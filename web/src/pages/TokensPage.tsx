import { useEffect, useMemo, useState } from "react";

import { getTokenAnalysis, type TokenAnalysis, type TokenCallRecord, type TokenMetricGroup, type TokenPayloadFieldGroup } from "../api/client";
import { BarChart } from "../components/BarChart";
import { MetricCard } from "../components/MetricCard";
import type { AppContext } from "../App";

type Props = {
  context: AppContext;
};

export function TokensPage({ context }: Props) {
  const [analysis, setAnalysis] = useState<TokenAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getTokenAnalysis(context.vaultPath)
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
  }, [context.vaultPath]);

  const flowAgentGroups = useMemo(() => buildFlowAgentGroups(analysis?.top_calls || []), [analysis]);

  if (loading && !analysis) {
    return <section className="panel"><p className="panel-copy">{context.t("loading")}</p></section>;
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
    <div className="page-stack">
      <section className="panel hero-panel compact-hero">
        <div>
          <h2>{context.t("tokensTitle")}</h2>
          <p>{context.t("tokensSubtitle")}</p>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard label={context.t("tokenMetricTotal")} value={formatNumber(totals.total_tokens)} hint={`${context.t("tokenMetricCalls")}: ${formatNumber(totals.call_count)}`} tone="blue" />
        <MetricCard label={context.t("tokenMetricPrompt")} value={formatNumber(totals.prompt_tokens)} hint={`${context.t("tokenMetricCompletion")}: ${formatNumber(totals.completion_tokens)}`} tone="teal" />
        <MetricCard label={context.t("tokenMetricCached")} value={formatNumber(totals.prompt_cached_tokens)} hint={`${context.t("tokenMetricCacheRate")}: ${formatPercent(totals.prompt_cache_rate)}`} tone="violet" />
        <MetricCard label={context.t("tokensPerSecond")} value={formatNumber(totals.tokens_per_second)} hint={`${formatNumber(totals.elapsed_seconds)}s`} tone="amber" />
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
                  <p>{`${context.t("tokenMetricCalls")}: ${formatNumber(flow.total.call_count)} · ${context.t("tokenMetricTotal")}: ${formatNumber(flow.total.total_tokens)}`}</p>
                </div>
                <span className="token-cache-pill">{`${context.t("tokenMetricCacheRate")}: ${formatPercent(flow.total.prompt_cache_rate)}`}</span>
              </div>
              <TokenTable context={context} rows={flow.agents} compact />
            </article>
          ))}
          {!flowAgentGroups.length && <p className="panel-copy">{context.t("tokenNoData")}</p>}
        </div>
      </section>

      <section className="two-column-grid">
        <PayloadFieldTable context={context} rows={analysis.by_payload_field || []} />
        <article className="panel">
          <div className="section-heading">
            <h2>{context.t("tokenPayloadDiagnosis")}</h2>
            <p>{context.t("tokenPayloadDiagnosisCopy")}</p>
          </div>
          <BarChart data={toPayloadBarData(analysis.by_payload_field || [])} limit={10} emptyText={context.t("tokenNoData")} />
        </article>
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>{context.t("tokenRecentRuns")}</h2>
        </div>
        <TokenTable context={context} rows={analysis.recent_runs} compact />
      </section>

      <section className="panel">
        <div className="section-heading">
          <h2>{context.t("tokenTopCalls")}</h2>
        </div>
        <TopCallsTable context={context} rows={analysis.top_calls} />
      </section>
    </div>
  );
}

type TokenMetricRow = Partial<TokenMetricGroup> & { run_id?: string };

function TokenTable({ context, title, rows, compact = false }: { context: AppContext; title?: string; rows: TokenMetricRow[]; compact?: boolean }) {
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
            {rows.map((row) => (
              <tr key={String(row.name || row.run_id)}>
                <td title={String(row.name || row.run_id)}>{String(row.name || row.run_id)}</td>
                <td>{formatNumber(row.call_count)}</td>
                <td>{formatNumber(row.total_tokens)}</td>
                {!compact && <td>{formatNumber(row.prompt_tokens)}</td>}
                {!compact && <td>{formatNumber(row.completion_tokens)}</td>}
                <td>{formatPercent(row.prompt_cache_rate)}</td>
              </tr>
            ))}
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
              <td>{row.flow || "unknown"}</td>
              <td>{row.agent || "unknown"}</td>
              <td title={row.source_file || ""}>{row.source_file || row.page_paths?.[0] || "unknown"}</td>
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
                <td>{row.name}</td>
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

type FlowAgentGroup = {
  name: string;
  total: TokenMetricGroup;
  agents: TokenMetricGroup[];
};

function buildFlowAgentGroups(calls: TokenCallRecord[]): FlowAgentGroup[] {
  const flows = new Map<string, Map<string, TokenMetricGroup>>();
  for (const call of calls) {
    const flow = call.flow || "unknown";
    const agent = call.agent || "unknown";
    if (!flows.has(flow)) flows.set(flow, new Map());
    const agents = flows.get(flow)!;
    const existing = agents.get(agent) || emptyMetric(agent);
    agents.set(agent, mergeMetric(existing, call));
  }
  const preferredOrder = ["ingest", "lint", "query", "unknown"];
  return [...flows.entries()]
    .sort(([left], [right]) => preferredOrderIndex(left, preferredOrder) - preferredOrderIndex(right, preferredOrder))
    .map(([name, agents]) => {
      const rows = [...agents.values()].sort((left, right) => (right.total_tokens || 0) - (left.total_tokens || 0));
      return {
        name,
        agents: rows,
        total: rows.reduce((acc, row) => mergeMetric(acc, row), emptyMetric(name)),
      };
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

function toPayloadBarData(rows: TokenPayloadFieldGroup[]): Record<string, number> {
  return Object.fromEntries(rows.slice(0, 10).map((row) => [row.name, row.payload_chars]));
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
