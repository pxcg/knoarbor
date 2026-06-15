import { useQuery } from "@tanstack/react-query";

import type { AppContext } from "../App";
import { getConfigDiagnostics, getSourceCatalog, type ConfigDiagnosticItem, type SourceConnectorCatalogItem } from "../api/client";
import { BrandIcon, type BrandIconName } from "../components/BrandIcon";
import { LoadingBlock } from "../components/LoadingBlock";
import { queryKeys } from "../queryKeys";
import { sortSourceConnectors, sourceDescription, sourceIconName, sourceSettingsFields, sourceTitle } from "../sourceCatalog";

type Props = {
  context: AppContext;
};

const processorCards = [
  {
    id: "mineru",
    icon: "mineru" as BrandIconName,
  },
];

export function SourcesPage({ context }: Props) {
  const diagnosticsQuery = useQuery({
    queryKey: ["config-diagnostics", context.configPath],
    queryFn: () => getConfigDiagnostics(context.configPath),
  });
  const catalogQuery = useQuery({
    queryKey: queryKeys.sourceCatalog(context.configPath),
    queryFn: () => getSourceCatalog(context.configPath),
    staleTime: 60_000,
  });
  const enabled = new Set(context.summary.enabled_connectors || []);
  const enabledProcessors = new Set(context.summary.enabled_document_processors || []);
  const connectorDiagnostics = new Map((diagnosticsQuery.data?.connectors || []).map((item) => [item.name, item]));
  const processorDiagnostics = new Map((diagnosticsQuery.data?.processors || []).map((item) => [item.name, item]));
  const connectors = sortSourceConnectors(catalogQuery.data?.connectors || []);

  return (
    <section className="view active">
      <div className="source-grid">
        {catalogQuery.isLoading && !connectors.length && <LoadingBlock title={context.t("sourceCatalogLoading")} copy={context.t("sourceCatalogLoadingCopy")} />}
        {connectors.map((source) => {
          const diagnostic = connectorDiagnostics.get(source.name);
          const isEnabled = diagnostic?.enabled ?? source.enabled ?? enabled.has(source.name);
          const icon = sourceIconName(source.name) || "generic_chat";
          return (
            <article className="source-card product-card" key={source.name}>
              <span className={`product-icon brand-product-icon brand-${source.name}`} aria-hidden="true">
                <BrandIcon name={icon} />
              </span>
              <span className="product-card-body">
                <span className="source-card-header">
                  <strong>{sourceTitle(source.name, context.t)}</strong>
                  <span className={`pill ${isEnabled && diagnostic?.ok !== false ? "success" : ""}`}>{statusLabel(diagnostic, isEnabled, context.t)}</span>
                </span>
                <p>{sourceDescription(source.name, context.t)}</p>
                <CapabilityRow catalog={source} diagnostic={diagnostic} t={context.t} fallback={source.name} />
                <SettingsSchemaFields catalog={source} t={context.t} />
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
          <button className="button secondary" type="button" onClick={context.openSettings}>
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
                    <strong>{sourceTitle(processor.id, context.t)}</strong>
                    <span className={`pill ${isEnabled && diagnostic?.ok !== false ? "success" : ""}`}>{statusLabel(diagnostic, isEnabled, context.t)}</span>
                  </span>
                  <p>{sourceDescription(processor.id, context.t)}</p>
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

function CapabilityRow({ catalog, diagnostic, fallback, t }: { catalog?: SourceConnectorCatalogItem; diagnostic?: ConfigDiagnosticItem; fallback: string; t: (key: string) => string }) {
  const chips: string[] = [];
  const sourceTypes = catalog?.source_types?.length ? catalog.source_types : diagnostic?.source_types;
  if (sourceTypes?.length) chips.push(...sourceTypes);
  if (catalog?.supports_checkpoint ?? diagnostic?.supports_checkpoint) chips.push(t("capabilityCheckpoint"));
  if (catalog?.supports_segmentation_hint ?? diagnostic?.supports_segmentation_hint) chips.push(t("capabilitySegmentation"));
  if (catalog?.requires_external_service ?? diagnostic?.requires_external_service) chips.push(t("capabilityExternalService"));
  if (catalog?.version || diagnostic?.version) chips.push(catalog?.version || diagnostic?.version || "");
  return (
    <span className="capability-row">
      {(chips.length ? chips : [fallback]).map((chip) => (
        <small key={chip}>{chip}</small>
      ))}
    </span>
  );
}

function SettingsSchemaFields({ catalog, t }: { catalog: SourceConnectorCatalogItem; t: (key: string) => string }) {
  const fields = sourceSettingsFields(catalog);
  if (!fields.length) return null;
  return (
    <details className="source-settings-details">
      <summary>{t("settingsFields")}</summary>
      <span className="capability-row">
        {fields.map((field) => (
          <small key={field}>{field}</small>
        ))}
      </span>
    </details>
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
