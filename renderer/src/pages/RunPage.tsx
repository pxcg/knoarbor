import { useCallback, useEffect, useState } from "react";

import { getRun } from "../api/client";
import type { RunAppContext } from "../appContext";
import { ChatIngestTargetModal } from "../components/ChatIngestTargetModal";
import { ExcerptIngestDialog } from "../components/ExcerptIngestDialog";
import { LineIcon } from "../components/LineIcon";
import { InlineHelp } from "../components/InlineHelp";
import { ActiveRunsPanel } from "../components/runs/RunPanels";
import { RunMonitorItem } from "../components/runs/RunMonitorItem";
import { flowStages } from "../components/runs/RunPanelModel";
import { sourceTitle } from "../sourceCatalog";
import { LatestWorkflowReport } from "./run/LatestWorkflowReport";
import { useRunLauncher, type IngestPreparation } from "./run/useRunLauncher";

type Props = {
  active?: boolean;
  context: RunAppContext;
  embedded?: boolean;
  mode: "ingest" | "lint";
};

export function RunPage({ active = true, context, embedded = false, mode }: Props) {
  const launcher = useRunLauncher(context, mode, active);
  const [focusedRun, setFocusedRun] = useState<Awaited<ReturnType<typeof getRun>> | null>(null);
  const [runNavigationError, setRunNavigationError] = useState<string | null>(null);
  const usesFileInput = launcher.localInputKind === "file";
  const usesFolderInput = launcher.localInputKind === "folder";
  const configuredInputScope = launcher.configuredInputScope;
  const canRunLocalInput = launcher.configReady && (
    (usesFileInput && Boolean(launcher.inputFilePath.trim())) ||
    (usesFolderInput && Boolean(launcher.inputFolderPath.trim()))
  );
  const canRunConfiguredInput = launcher.configReady && (
    Boolean(configuredInputScope) && (configuredInputScope !== "knoarbor_chat" || Boolean(launcher.selectedChatSessionId))
  );

  useEffect(() => {
    setFocusedRun(null);
    setRunNavigationError(null);
  }, [context.activeVaultId]);

  useEffect(() => {
    const target = context.navigationTarget;
    const targetMode = target?.kind === "run" && target.flow === "lint" ? "lint" : "ingest";
    if (!active || target?.kind !== "run" || target.vaultId !== context.activeVaultId || targetMode !== mode) return;
    let cancelled = false;
    getRun(context.activeVaultSelector, target.runId)
      .then((run) => {
        if (cancelled) return;
        setFocusedRun(run);
        setRunNavigationError(null);
        context.consumeNavigationTarget(target.requestId);
      })
      .catch(() => {
        if (cancelled) return;
        setFocusedRun(null);
        setRunNavigationError(context.language === "zh" ? "目标运行记录不存在或已被删除。" : "The requested run does not exist or was deleted.");
        context.consumeNavigationTarget(target.requestId);
      });
    return () => { cancelled = true; };
  }, [active, context.activeVaultId, context.activeVaultSelector, context.consumeNavigationTarget, context.language, context.navigationTarget, mode]);

  const retainFocusedTerminalRun = useCallback((run: Awaited<ReturnType<typeof getRun>>) => {
    setFocusedRun((current) => current?.run_id === run.run_id ? run : current);
  }, []);

  return (
    <section className={embedded ? "embedded-section" : "view active"}>
      <div className="panel-grid single-run-grid">
        {mode !== "lint" && <article className="panel run-card">
          <div className="panel-header">
            <div>
              <h2>
                {context.t("ingestTitle")}
                <InlineHelp text={context.t("ingestSubtitle")} />
              </h2>
            </div>
          </div>
          <div className="import-source-cards">
            <section className="import-source-card">
              <div className="import-source-card-top">
                <div className="import-source-card-heading">
                  <span className="import-source-icon">
                    <LineIcon name="wiki" />
                  </span>
                  <div>
                    <strong>
                      {context.t("importLocalFilesTitle")}
                      <InlineHelp text={context.t("importLocalFilesCopy")} />
                    </strong>
                  </div>
                </div>
                <button
                  className="button primary import-card-run"
                  type="button"
                  disabled={!canRunLocalInput || launcher.ingestSubmitting}
                  onClick={() => void launcher.startIngest(usesFolderInput ? "folder" : "file")}
                >
                  {context.t("runIngest")}
                </button>
              </div>
              <div className="import-primary-actions">
                {launcher.canSelectFile && (
                  <button
                    className={`button ${usesFileInput ? "primary" : "secondary"}`}
                    type="button"
                    onClick={() => launcher.setLocalInputKind("file")}
                  >
                    {context.t("chooseInputFile")}
                  </button>
                )}
                {launcher.canSelectDirectory && (
                  <button
                    className={`button ${usesFolderInput ? "primary" : "secondary"}`}
                    type="button"
                    onClick={() => launcher.setLocalInputKind("folder")}
                  >
                    {context.t("chooseInputFolder")}
                  </button>
                )}
              </div>
              {usesFileInput && (
                <label className="field import-path-field">
                  <span>{context.t("inputFilePath")}</span>
                  <div className="run-path-row">
                    <input value={launcher.inputFilePath} onChange={(event) => launcher.setInputFilePath(event.target.value)} placeholder={context.t("inputFilePathPlaceholder")} />
                    {launcher.canSelectFile && (
                      <button className="button secondary" type="button" onClick={() => void launcher.chooseInputFile()}>
                        {context.t("chooseFile")}
                      </button>
                    )}
                  </div>
                </label>
              )}
              {usesFolderInput && (
                <label className="field import-path-field">
                  <span>{context.t("inputFolderPath")}</span>
                  <div className="run-path-row">
                    <input value={launcher.inputFolderPath} onChange={(event) => launcher.setInputFolderPath(event.target.value)} placeholder={context.t("inputFolderPathPlaceholder")} />
                    {launcher.canSelectDirectory && (
                      <button className="button secondary" type="button" onClick={() => void launcher.chooseInputFolder()}>
                        {context.t("chooseFolder")}
                      </button>
                    )}
                  </div>
                </label>
              )}
            </section>

            <section className="import-source-card">
              <div className="import-source-card-top">
                <div className="import-source-card-heading">
                  <span className="import-source-icon">
                    <LineIcon name="sources" />
                  </span>
                  <div>
                    <strong>
                      {context.t("importConfiguredSourcesTitle")}
                      <InlineHelp text={context.t("importConfiguredSourcesCopy")} />
                    </strong>
                  </div>
                </div>
                <button
                  className="button primary import-card-run"
                  type="button"
                  disabled={!canRunConfiguredInput || launcher.ingestSubmitting}
                  onClick={() => void launcher.startIngest(configuredInputScope)}
                >
                  {context.t("runIngest")}
                </button>
              </div>
              <label className="field compact-field">
                <span>{context.t("inputsToRun")}</span>
                <select value={configuredInputScope} onChange={(event) => launcher.setConfiguredInputScope(event.target.value)} disabled={!launcher.configuredInputOptions.length}>
                  {launcher.configuredInputOptions.length ? launcher.configuredInputOptions.map((option) => (
                    <option value={option.name} key={option.name}>
                      {option.name === "knoarbor_chat" ? option.title : sourceTitle(option.name, context.t)}
                    </option>
                  )) : (
                    <option value="">{context.t("noConfiguredChatSources")}</option>
                  )}
                </select>
              </label>
              {configuredInputScope === "knoarbor_chat" && (
                <label className="field compact-field">
                  <span>{context.t("selectChatSession")}</span>
                  <select
                    value={launcher.selectedChatSessionId}
                    onChange={(event) => launcher.setSelectedChatSessionId(event.target.value)}
                    disabled={launcher.chatSessionsLoading || !launcher.chatSessions.length}
                  >
                    {launcher.chatSessions.length ? launcher.chatSessions.map((session) => (
                      <option value={session.session_id} key={session.session_id}>
                        {session.title || session.session_id}
                      </option>
                    )) : (
                      <option value="">{context.t("noChatSessionsToIngest")}</option>
                    )}
                  </select>
                </label>
              )}
            </section>

            <section className="import-source-card custom-input-card">
              <div className="import-source-card-top">
                <div className="import-source-card-heading">
                  <span className="import-source-icon">
                    <LineIcon name="manual-input" />
                  </span>
                  <div>
                    <strong>
                      {context.t("customInputTitle")}
                      <InlineHelp text={context.t("customInputCopy")} />
                    </strong>
                  </div>
                </div>
                <button
                  className="button primary import-card-run"
                  type="button"
                  disabled={!launcher.configReady || !context.vaultOptions.some((vault) => !vault.virtual)}
                  onClick={launcher.openCustomInput}
                >
                  {context.t("customInputOpen")}
                </button>
              </div>
              <p className="panel-copy custom-input-card-copy">{context.t("customInputDescription")}</p>
            </section>
          </div>
          <p className="panel-copy">{context.t("runIngestCopy")}</p>
        </article>}

        {mode !== "ingest" && <article className="panel run-card">
          <div className="panel-header">
            <div>
              <h2>
                {context.t("lintTitle")}
                <InlineHelp text={context.t("lintSubtitle")} />
              </h2>
            </div>
            <button className="button primary" disabled={!launcher.configReady} onClick={launcher.startLint}>
              {context.t("runLint")}
            </button>
          </div>
          {!launcher.configReady && <p className="panel-copy warning">{context.t("configRequired")}</p>}
        </article>}
      </div>

      {runNavigationError && <p className="settings-action-note warning" role="alert">{runNavigationError}</p>}
      {launcher.launchError && !launcher.customInputDraft && <p className="settings-action-note warning" role="alert">{launcher.launchError}</p>}
      {active && focusedRun && <RunMonitorItem context={context} onTerminal={retainFocusedTerminalRun} run={focusedRun} />}
      {active && (
        launcher.activePreparation
          ? <IngestPreparationPanel context={context} preparation={launcher.activePreparation} />
          : <ActiveRunsPanel context={context} excludeRunId={focusedRun?.run_id} flow={mode} includeRecoverable={mode === "ingest"} />
      )}
      {active && <LatestWorkflowReport context={context} mode={mode} />}
      {mode === "ingest" && (
        <>
          <ChatIngestTargetModal
            context={context}
            isOpen={launcher.chatIngestOpen}
            title={launcher.chatIngestTitle}
            targetVaultId={launcher.chatIngestTargetVaultId}
            submitting={launcher.chatIngestSubmitting}
            onTitleChange={launcher.setChatIngestTitle}
            onTargetVaultChange={launcher.setChatIngestTargetVaultId}
            onCancel={() => !launcher.chatIngestSubmitting && launcher.setChatIngestOpen(false)}
            onConfirm={() => void launcher.confirmChatSessionIngest()}
          />
          <ExcerptIngestDialog
            context={context}
            draft={launcher.customInputDraft}
            error={launcher.launchError}
            submitting={launcher.customInputSubmitting}
            onChange={launcher.setCustomInputDraft}
            onCancel={() => !launcher.customInputSubmitting && launcher.closeCustomInput()}
            onConfirm={() => void launcher.confirmCustomInput()}
          />
        </>
      )}
    </section>
  );
}

function IngestPreparationPanel({ context, preparation }: { context: RunAppContext; preparation: IngestPreparation }) {
  const messageKey = preparation.kind === "document"
    ? "ingestPreparingDocument"
    : "ingestPreparingFolder";
  const stages = flowStages("ingest");
  return (
    <article className="panel run-monitor-panel" aria-live="polite">
      <div className="panel-header compact">
        <div>
          <h2>{context.t("runMonitor")}</h2>
          <p className="panel-copy">{context.t(messageKey)}</p>
        </div>
      </div>
      <div className="run-flow-placeholder ingest-preparation-panel">
        <section className="run-placeholder-flow">
          <h3>{preparation.inputPath || context.t("importMaterials")}</h3>
          <div className="run-stage-steps">
            {stages.map((stage) => (
              <span
                className={`run-stage-step placeholder ${
                  stage.key === "queued" || stage.key === "input"
                    ? "done"
                    : stage.key === "document_process"
                    ? "active"
                    : ""
                }`}
                key={stage.key}
              >
                <span />
                <small>{context.t(stage.label)}</small>
              </span>
            ))}
          </div>
          <div className="progress-track indeterminate" role="progressbar" aria-label={context.t(messageKey)}>
            <span />
          </div>
        </section>
      </div>
    </article>
  );
}
