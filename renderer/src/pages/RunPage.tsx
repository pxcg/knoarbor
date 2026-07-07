import type { AppContext } from "../appContext";
import { LineIcon } from "../components/LineIcon";
import { InlineHelp } from "../components/InlineHelp";
import { ActiveRunsPanel } from "../components/runs/RunPanels";
import { sourceTitle } from "../sourceCatalog";
import { LatestWorkflowReport } from "./run/LatestWorkflowReport";
import { useRunLauncher } from "./run/useRunLauncher";

type Props = {
  context: AppContext;
  embedded?: boolean;
  mode: "ingest" | "lint";
};

export function RunPage({ context, embedded = false, mode }: Props) {
  const launcher = useRunLauncher(context, mode);
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
                  disabled={!canRunLocalInput}
                  onClick={() => launcher.startIngest(usesFolderInput ? "folder" : "file")}
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
                  disabled={!canRunConfiguredInput}
                  onClick={() => launcher.startIngest(configuredInputScope)}
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
          <div className="lint-mode-picker" role="radiogroup" aria-label={context.t("mode")}>
            {[
              { value: "deterministic", label: context.t("structuredMaintenance") },
              { value: "semantic", label: context.t("semanticMaintenance") },
            ].map((item) => (
              <button
                aria-checked={launcher.lintMode === item.value}
                className={`lint-mode-option ${launcher.lintMode === item.value ? "active" : ""}`}
                key={item.value}
                onClick={() => launcher.setLintMode(item.value)}
                role="radio"
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
          {!launcher.configReady && <p className="panel-copy warning">{context.t("configRequired")}</p>}
        </article>}
      </div>

      <ActiveRunsPanel context={context} flow={mode} includeRecoverable={mode === "ingest"} />
      <LatestWorkflowReport context={context} mode={mode} />
    </section>
  );
}
