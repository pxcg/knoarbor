import type { AppContext } from "../appContext";
import { LineIcon } from "../components/LineIcon";
import { RunFlowGuide } from "../components/runs/RunPanels";
import { sourceTitle } from "../sourceCatalog";
import { LatestWorkflowReport } from "./run/LatestWorkflowReport";
import { useRunLauncher } from "./run/useRunLauncher";

type Props = {
  context: AppContext;
  embedded?: boolean;
  mode?: "both" | "ingest" | "lint";
  showFlowGuide?: boolean;
};

export function RunPage({ context, embedded = false, mode = "both", showFlowGuide }: Props) {
  const launcher = useRunLauncher(context, mode);
  const isSingleMode = mode !== "both";
  const shouldShowFlowGuide = showFlowGuide ?? (!embedded && mode === "both");
  const usesFileInput = launcher.inputScope === "file";
  const usesFolderInput = launcher.inputScope === "folder";
  const usesConfiguredSource = !usesFileInput && !usesFolderInput;
  const configuredInputScope = usesConfiguredSource ? launcher.inputScope : "enabled";

  return (
    <section className={embedded ? "embedded-section" : "view active"}>
      {shouldShowFlowGuide && <RunFlowGuide context={context} mode={mode} />}

      <div className={`panel-grid ${isSingleMode ? "single-run-grid" : ""}`}>
        {mode !== "lint" && <article className="panel run-card">
          <div className="panel-header">
            <div>
              <h2>{context.t("ingestTitle")}</h2>
              <p className="panel-copy">{context.t("ingestSubtitle")}</p>
            </div>
            <button
              className="button primary"
              disabled={
                !launcher.configReady ||
                (launcher.inputScope === "file" && !launcher.inputFilePath.trim()) ||
                (launcher.inputScope === "folder" && !launcher.inputFolderPath.trim()) ||
                (launcher.inputScope === "knoarbor_chat" && !launcher.selectedChatSessionId)
              }
              onClick={launcher.startIngest}
            >
              {context.t("runIngest")}
            </button>
          </div>
          <div className="import-source-cards">
            <section className={`import-source-card ${usesFileInput || usesFolderInput ? "active" : ""}`}>
              <div className="import-source-card-heading">
                <span className="import-source-icon">
                  <LineIcon name="wiki" />
                </span>
                <div>
                  <strong>{context.t("importLocalFilesTitle")}</strong>
                  <p className="panel-copy">{context.t("importLocalFilesCopy")}</p>
                </div>
              </div>
              <div className="import-primary-actions">
                {launcher.canSelectFile && (
                  <button
                    className={`button ${usesFileInput ? "primary" : "secondary"}`}
                    type="button"
                    onClick={() => {
                      launcher.setInputScope("file");
                      void launcher.chooseInputFile();
                    }}
                  >
                    {context.t("chooseInputFile")}
                  </button>
                )}
                {launcher.canSelectDirectory && (
                  <button
                    className={`button ${usesFolderInput ? "primary" : "secondary"}`}
                    type="button"
                    onClick={() => {
                      launcher.setInputScope("folder");
                      void launcher.chooseInputFolder();
                  }}
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

            <section className={`import-source-card ${usesConfiguredSource ? "active" : ""}`}>
              <div className="import-source-card-heading">
                <span className="import-source-icon">
                  <LineIcon name="sources" />
                </span>
                <div>
                  <strong>{context.t("importConfiguredSourcesTitle")}</strong>
                  <p className="panel-copy">{context.t("importConfiguredSourcesCopy")}</p>
                </div>
              </div>
              <label className="field compact-field">
                <span>{context.t("inputsToRun")}</span>
                <select value={configuredInputScope} onFocus={() => launcher.setInputScope(configuredInputScope)} onChange={(event) => launcher.setInputScope(event.target.value)}>
                  <option value="enabled">{context.t("enabledConnectors")}</option>
                  <option value="knoarbor_chat">{context.t("knoarborChatConnector")}</option>
                  {launcher.connectorOptions.map((connector) => (
                    <option value={connector.name} key={connector.name}>
                      {sourceTitle(connector.name, context.t)}
                    </option>
                  ))}
                  <option value="custom">{context.t("customConnectorList")}</option>
                </select>
              </label>
            </section>
          </div>
          {launcher.inputScope === "knoarbor_chat" && (
            <label className="field">
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
              <small>{context.t("knoarborChatInputHint")}</small>
            </label>
          )}
          {launcher.inputScope === "custom" && (
            <label className="field">
              <span>{context.t("connectorNames")}</span>
              <input value={launcher.connectors} onChange={(event) => launcher.setConnectors(event.target.value)} placeholder={context.t("connectorNamesPlaceholder")} />
            </label>
          )}
          <p className="panel-copy">{context.t("runIngestCopy")}</p>
        </article>}

        {mode !== "ingest" && <article className="panel run-card">
          <div className="panel-header">
            <div>
              <h2>{context.t("lintTitle")}</h2>
              <p className="panel-copy">{context.t("lintSubtitle")}</p>
            </div>
            <button className="button primary" disabled={!launcher.configReady} onClick={launcher.startLint}>
              {context.t("runLint")}
            </button>
          </div>
          <label className="field">
            <span>{context.t("mode")}</span>
            <select value={launcher.lintMode} onChange={(event) => launcher.setLintMode(event.target.value)}>
              <option value="deterministic">{context.t("structuredMaintenance")}</option>
              <option value="semantic">{context.t("semanticMaintenance")}</option>
            </select>
          </label>
          {!launcher.configReady && <p className="panel-copy warning">{context.t("configRequired")}</p>}
        </article>}
      </div>

      <article className="panel">
        <div className="panel-header">
          <h2>{context.t("runOutput")}</h2>
          <button className="button secondary" onClick={() => launcher.setRunOutput(context.t("noRunYet"))}>
            {context.t("clear")}
          </button>
        </div>
        <pre className={`output ${launcher.runOutput === context.t("noRunYet") ? "output-idle" : ""}`}>{launcher.runOutput}</pre>
      </article>
      <LatestWorkflowReport context={context} mode={mode} />
    </section>
  );
}
