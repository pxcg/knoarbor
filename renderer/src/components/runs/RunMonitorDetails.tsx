import type { RunAppContext } from "../../appContext";
import { userFacingError } from "../../userFacingError";
import type { RunEvent, RunRecord } from "../../types";
import {
  asRecord,
  currentSourceInfo,
  currentStageKey,
  currentStageLabel,
  eventNodeKey,
  flowStages,
  localizeRunEventMessage,
  numberValue,
  reportPathForRun,
  runResultItems,
  runStageMetrics,
  stageLabel,
  writtenPageCount,
  type RunSourceInfo,
} from "./RunPanelModel";

export function RunSummaryBox({ context, events, run }: { context: RunAppContext; events: RunEvent[]; run: RunRecord }) {
  const metrics = asRecord(run.metrics);
  const stats = asRecord(run.result_summary?.stats);
  const semanticCalls = numberValue(metrics.semantic_call_count) ?? numberValue(asRecord(metrics.semantic).semantic_call_count) ?? latestEventNumber(events, ["semantic_call_count", "semantic_calls"]);
  const totalTokens = numberValue(metrics.total_tokens) ?? numberValue(asRecord(metrics.semantic).total_tokens) ?? latestEventNumber(events, ["total_tokens"]);
  const writtenPages = writtenPageCount(run.result_summary?.written_pages) ?? numberValue(stats.written_count) ?? latestEventNumber(events, ["written_pages", "written_count"]);
  const reportPath = reportPathForRun(run);
  const items = [
    { label: context.t("stage"), value: currentStageLabel(run, context.t) },
    { label: context.t("elapsed"), value: `${Math.round(run.elapsed_seconds)}s` },
    { label: context.t("recentEvents"), value: String(events.length) },
    semanticCalls !== undefined ? { label: context.t("semanticCallsShort"), value: semanticCalls.toLocaleString() } : null,
    totalTokens !== undefined ? { label: context.t("totalTokensShort"), value: totalTokens.toLocaleString() } : null,
    writtenPages !== undefined ? { label: context.t("writtenPagesShort"), value: writtenPages.toLocaleString() } : null,
  ].filter((item): item is { label: string; value: string } => Boolean(item));
  return (
    <div className="run-summary-box">
      <h3>{context.t("runSummary")}</h3>
      <dl>
        {items.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
      <small>{reportPath ? reportPath : context.t("noReportYet")}</small>
    </div>
  );
}

export function RunFlowPlaceholder({ context, flow }: { context: RunAppContext; flow?: RunRecord["flow"] }) {
  const flows = [
    { key: "ingest", title: context.t("importMaterials"), stages: flowStages("ingest") },
    { key: "lint", title: context.t("lintTitle"), stages: flowStages("lint") },
  ].filter((item) => !flow || item.key === flow);
  return (
    <div className="run-flow-placeholder" aria-label={context.t("runStageTrack")}>
      {flows.map((flow) => (
        <section className="run-placeholder-flow" key={flow.key}>
          <h3>{flow.title}</h3>
          <div className="run-stage-steps">
            {flow.stages.map((stage) => (
              <span className={`run-stage-step placeholder ${stage.kind === "agent" ? "agent" : ""}`} key={stage.key}>
                <span />
                <small>{context.t(stage.label)}</small>
              </span>
            ))}
          </div>
        </section>
      ))}
      <div className="run-placeholder-note">{context.t("noRunYet")}</div>
    </div>
  );
}

export function RunNodeDetails({ context, events, run, selectedNode }: { context: RunAppContext; events: RunEvent[]; run: RunRecord; selectedNode: string }) {
  const nodes = flowStages(run.flow);
  const node = nodes.find((item) => item.key === selectedNode) || nodes[0];
  const nodeEvents = events.filter((event) => eventNodeKey(event, run.flow) === node.key);
  const fallbackMessage = node.key === currentStageKey(run) ? run.message || run.stage : context.t("noNodeEvents");
  const resultItems = node.key === "done" ? runResultItems(run, context.t) : [];
  return (
    <section className="run-node-details">
      <div className="run-node-details-header">
        <div>
          <h3>{context.t("nodeDetails")}</h3>
          <p>{context.t(node.label)}</p>
        </div>
        <span>{node.kind === "agent" ? context.t("agentNode") : context.t("workflowNode")}</span>
      </div>
      {resultItems.length ? (
        <dl className="run-node-result">
          {resultItems.map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : nodeEvents.length ? (
        <div className="run-node-events">
          {nodeEvents.map((event) => (
            <article className="run-node-event" key={`${event.run_id}:${event.sequence}`}>
              <span className={event.status === "failed" || event.status === "partially_failed" ? "danger" : event.status === "completed" ? "success" : ""} />
              <div>
                <strong>{localizeRunEventMessage(event.message, event.event_type, context.t)}</strong>
                <small>
                  {stageLabel(event, context.t)} · {event.created_at}
                </small>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="panel-copy">{fallbackMessage}</p>
      )}
    </section>
  );
}

export function RunStageTrack({
  context,
  events,
  onSelect,
  run,
  selectedNode,
}: {
  context: RunAppContext;
  events: RunEvent[];
  onSelect: (node: string) => void;
  run: RunRecord;
  selectedNode: string;
}) {
  const stages = flowStages(run.flow);
  const current = currentStageKey(run);
  const currentIndex = stages.findIndex((stage) => stage.key === current);
  const metrics = runStageMetrics(run);
  const eventCounts = new Map<string, number>();
  for (const event of events) {
    const key = eventNodeKey(event, run.flow);
    eventCounts.set(key, (eventCounts.get(key) || 0) + 1);
  }
  return (
    <div className="run-stage-track" aria-label={context.t("runStageTrack")}>
      <div className="run-stage-steps">
        {stages.map((stage, index) => {
          const active = stage.key === current;
          const done = currentIndex >= 0 && index < currentIndex;
          return (
            <button
              className={`run-stage-step ${active ? "active" : ""} ${done ? "done" : ""} ${selectedNode === stage.key ? "selected" : ""} ${stage.kind === "agent" ? "agent" : ""}`}
              key={stage.key}
              onClick={() => onSelect(stage.key)}
              title={context.t(stage.label)}
              type="button"
            >
              <span />
              <small>{context.t(stage.label)}</small>
              {!!eventCounts.get(stage.key) && <em>{eventCounts.get(stage.key)}</em>}
            </button>
          );
        })}
      </div>
      {!!metrics.length && (
        <div className="run-stage-metrics">
          {metrics.map((metric) => (
            <span key={metric.label}>
              {context.t(metric.label)}: {metric.value}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function RunSourceBadge({ info }: { info: RunSourceInfo }) {
  return (
    <span className="run-source-name" title={info.detail ? `${info.label}: ${info.detail}` : info.label}>
      {info.detail || info.label}
    </span>
  );
}

export function RunErrorBox({ context, run }: { context: RunAppContext; run: RunRecord }) {
  if (!hasRunErrorInfo(run) || !run.error_info) return null;
  return (
    <div className="run-error-box">
      <strong>{context.t("error")}</strong>
      <span>{userFacingError(run.error_info.message || run.error, context.language)}</span>
    </div>
  );
}

function latestEventNumber(events: RunEvent[], keys: string[]): number | undefined {
  for (const event of events.slice().reverse()) {
    const sources = [asRecord(event.metrics), asRecord(asRecord(event.metrics).semantic), asRecord(event.payload)];
    for (const source of sources) {
      for (const key of keys) {
        const value = numberValue(source[key]);
        if (value !== undefined) return value;
      }
    }
  }
  return undefined;
}

function hasRunErrorInfo(run: RunRecord) {
  const info = run.error_info;
  if (!info) return false;
  return Boolean(info.code || info.message || info.hint || info.error_type || run.error);
}
