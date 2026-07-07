import type { ModelProviderProbeState } from "../../api/client";

export function ModelProbeResultPanel({
  result,
  t,
  activeModel,
  onSelectModel,
}: {
  result?: ModelProviderProbeState;
  t: (key: string) => string;
  activeModel?: string;
  onSelectModel?: (model: string) => void;
}) {
  if (!result?.discovery) {
    return <p className="settings-action-note">{t("modelProbeEmpty")}</p>;
  }
  const discovery = result.discovery;
  const modelIds = discovery?.model_ids || [];
  return (
    <section className="model-probe-panel">
      <div className="model-probe-header">
        <h3>{t("modelProbeResult")}</h3>
        <span className={`pill ${discovery?.status === "ok" ? "success" : discovery?.status === "error" ? "danger" : ""}`}>
          {discovery?.status || t("unknown")}
        </span>
      </div>
      <p className="panel-copy">{discovery?.message}</p>
      <dl className="model-probe-grid">
        <div>
          <dt>{t("detectedContextWindow")}</dt>
          <dd>{formatMaybeNumber(discovery?.detected_context_window, t)}</dd>
        </div>
        <div>
          <dt>{t("effectiveContextWindow")}</dt>
          <dd>{formatMaybeNumber(discovery?.effective_context_window, t)}</dd>
        </div>
        <div>
          <dt>{t("modelCount")}</dt>
          <dd>{formatMaybeNumber(discovery?.model_count, t)}</dd>
        </div>
      </dl>
      {discovery?.configured_model_found === false && activeModel && <p className="settings-action-note warning">{t("configuredModelMissing")}</p>}
      {modelIds.length > 0 && (
        <div className="model-discovery-list">
          <div className="model-discovery-heading">
            <h4>{t("availableModels")}</h4>
            <span>{t("availableModelsCopy")}</span>
          </div>
          <div className="model-discovery-table" role="table" aria-label={t("availableModels")}>
            {modelIds.map((modelId) => {
              const selected = modelId === activeModel;
              return (
                <div className={`model-discovery-row ${selected ? "selected" : ""}`} role="row" key={modelId}>
                  <span className="model-discovery-name" title={modelId}>
                    {modelId}
                  </span>
                  <button className={selected ? "button ghost compact" : "button secondary compact"} type="button" onClick={() => onSelectModel?.(modelId)} disabled={selected}>
                    {selected ? t("selectedModel") : t("useModel")}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

function formatMaybeNumber(value: number | null | undefined, t: (key: string) => string): string {
  return typeof value === "number" ? value.toLocaleString() : t("notAvailable");
}
