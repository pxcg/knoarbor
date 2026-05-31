import { useQuery } from "@tanstack/react-query";

import type { AppContext } from "../App";
import { getConfigDiagnostics, type ConfigDiagnosticItem } from "../api/client";
import { BrandIcon, type BrandIconName } from "../components/BrandIcon";

type Props = {
  context: AppContext;
};

const sourceCards = [
  {
    id: "markdown",
    title: "Markdown",
    descriptionKey: "sourceMarkdownDescription",
    icon: "markdown" as BrandIconName,
    tone: "blue",
  },
  {
    id: "hermes",
    title: "Hermes",
    descriptionKey: "sourceHermesDescription",
    icon: "hermes" as BrandIconName,
    tone: "teal",
  },
  {
    id: "codex",
    title: "Codex",
    descriptionKey: "sourceCodexDescription",
    icon: "codex" as BrandIconName,
    tone: "violet",
  },
  {
    id: "openclaw",
    title: "OpenClaw",
    descriptionKey: "sourceOpenClawDescription",
    icon: "openclaw" as BrandIconName,
    tone: "emerald",
  },
  {
    id: "claude_code",
    title: "Claude Code",
    descriptionKey: "sourceClaudeCodeDescription",
    icon: "claude_code" as BrandIconName,
    tone: "slate",
  },
  {
    id: "generic_chat",
    title: "Custom chat",
    descriptionKey: "sourceGenericChatDescription",
    icon: "generic_chat" as BrandIconName,
    tone: "blue",
  },
];

const processorCards = [
  {
    id: "mineru",
    title: "MinerU Adapter",
    descriptionKey: "sourceMineruDescription",
    icon: "mineru" as BrandIconName,
    tone: "amber",
  },
];

export function SourcesPage({ context }: Props) {
  const diagnosticsQuery = useQuery({
    queryKey: ["config-diagnostics", context.configPath],
    queryFn: () => getConfigDiagnostics(context.configPath),
  });
  const enabled = new Set(context.summary.enabled_connectors || []);
  const enabledProcessors = new Set(context.summary.enabled_document_processors || []);
  const connectorDiagnostics = new Map((diagnosticsQuery.data?.connectors || []).map((item) => [item.name, item]));
  const processorDiagnostics = new Map((diagnosticsQuery.data?.processors || []).map((item) => [item.name, item]));

  return (
    <section className="view active">
      <div className="page-intro">
        <div>
          <p className="eyebrow">{context.t("sourceLayer")}</p>
          <h2>{context.t("sourceOverview")}</h2>
          <p className="panel-copy">{context.t("sourceSubtitle")}</p>
        </div>
      </div>

      <div className="source-grid">
        {sourceCards.map((source) => {
          const diagnostic = connectorDiagnostics.get(source.id);
          const isEnabled = diagnostic?.enabled ?? enabled.has(source.id);
          return (
            <article className="source-card product-card" key={source.id}>
              <span className={`product-icon brand-product-icon brand-${source.id}`} aria-hidden="true">
                <BrandIcon name={source.icon} />
              </span>
              <span className="product-card-body">
                <span className="source-card-header">
                  <strong>{source.title}</strong>
                  <span className={`pill ${isEnabled && diagnostic?.ok !== false ? "success" : ""}`}>{statusLabel(diagnostic, isEnabled, context.t)}</span>
                </span>
                <p>{context.t(source.descriptionKey)}</p>
                <CapabilityRow diagnostic={diagnostic} t={context.t} fallback={source.id} />
                {isEnabled && diagnostic?.ok === false && <small className="source-warning">{diagnosticDetail(diagnostic, context.t)}</small>}
              </span>
            </article>
          );
        })}
      </div>

      <article className="panel source-flow-panel">
        <div className="panel-header">
          <div>
            <h2>{context.t("sourceFlowTitle")}</h2>
            <p className="panel-copy">{context.t("sourceFlowCopy")}</p>
          </div>
          <button className="button secondary" type="button" onClick={() => context.navigate("settings")}>
            {context.t("openSettings")}
          </button>
        </div>
        <div className="source-flow">
          <span>{context.t("sourceFlowRaw")}</span>
          <strong>→</strong>
          <span>{context.t("sourceFlowPreprocess")}</span>
          <strong>→</strong>
          <span>{context.t("sourceFlowMarkdown")}</span>
          <strong>→</strong>
          <span>{context.t("sourceFlowIngest")}</span>
        </div>
      </article>

      <article className="panel">
        <div className="panel-header">
          <div>
            <h2>{context.t("documentPreprocessing")}</h2>
            <p className="panel-copy">{context.t("documentPreprocessingCopy")}</p>
          </div>
        </div>
        <div className="source-grid compact-source-grid">
          {processorCards.map((processor) => {
            const diagnostic = processorDiagnostics.get(processor.id);
            const isEnabled = diagnostic?.enabled ?? enabledProcessors.has(processor.id);
            return (
              <article className="source-card product-card" key={processor.id}>
                <span className={`product-icon brand-product-icon brand-${processor.id}`} aria-hidden="true">
                  <BrandIcon name={processor.icon} />
                </span>
                <span className="product-card-body">
                  <span className="source-card-header">
                    <strong>{processor.title}</strong>
                    <span className={`pill ${isEnabled && diagnostic?.ok !== false ? "success" : ""}`}>{statusLabel(diagnostic, isEnabled, context.t)}</span>
                  </span>
                  <p>{context.t(processor.descriptionKey)}</p>
                  <small>{context.t("preprocessor")}</small>
                  {isEnabled && diagnostic?.ok === false && <small className="source-warning">{diagnosticDetail(diagnostic, context.t)}</small>}
                </span>
              </article>
            );
          })}
        </div>
      </article>

      <article className="panel">
        <div className="panel-header">
          <div>
            <h2>{context.t("configured")}</h2>
            <p className="panel-copy">{context.t("sourceNote")}</p>
          </div>
        </div>
        <dl className="detail-list">
          <div>
            <dt>{context.t("vault")}</dt>
            <dd>{context.vaultPath}</dd>
          </div>
          <div>
            <dt>{context.t("connectors")}</dt>
            <dd>{context.summary.enabled_connectors?.join(", ") || context.t("notConfigured")}</dd>
          </div>
          <div>
            <dt>{context.t("documentPreprocessing")}</dt>
            <dd>{context.summary.enabled_document_processors?.join(", ") || context.t("notConfigured")}</dd>
          </div>
          <div>
            <dt>{context.t("sources")}</dt>
            <dd>{context.status?.raw_sources ?? "--"}</dd>
          </div>
        </dl>
      </article>
    </section>
  );
}

function CapabilityRow({ diagnostic, fallback, t }: { diagnostic?: ConfigDiagnosticItem; fallback: string; t: (key: string) => string }) {
  const chips: string[] = [];
  if (diagnostic?.source_types?.length) chips.push(...diagnostic.source_types);
  if (diagnostic?.supports_checkpoint) chips.push(t("capabilityCheckpoint"));
  if (diagnostic?.supports_segmentation_hint) chips.push(t("capabilitySegmentation"));
  if (diagnostic?.requires_external_service) chips.push(t("capabilityExternalService"));
  if (diagnostic?.version) chips.push(diagnostic.version);
  return (
    <span className="capability-row">
      {(chips.length ? chips : [fallback]).map((chip) => (
        <small key={chip}>{chip}</small>
      ))}
    </span>
  );
}

function statusLabel(diagnostic: ConfigDiagnosticItem | undefined, enabled: boolean, t: (key: string) => string) {
  if (!enabled) return t("disabled");
  if (diagnostic?.ok === false) return t("needsAttention");
  return t("enabled");
}

function diagnosticDetail(diagnostic: ConfigDiagnosticItem, t: (key: string) => string) {
  const key = `diagnosticCode.${diagnostic.code}`;
  const translated = t(key);
  const label = translated === key ? diagnostic.code : translated;
  return diagnostic.detail ? `${label}: ${diagnostic.detail}` : label;
}
