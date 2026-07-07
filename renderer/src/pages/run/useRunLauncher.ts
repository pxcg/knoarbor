import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getSourceCatalog, ingestChatSession, listChatSessions, runIngest, runIngestFile, runIngestFolder, runLint } from "../../api/client";
import type { AppContext } from "../../appContext";
import { runStatusLabel } from "../../components/runStatus";
import { canSelectDesktopDirectory, canSelectDesktopFile, selectDesktopDirectory, selectDesktopFile } from "../../desktop/desktopBridge";
import { queryKeys } from "../../queryKeys";
import { sortSourceConnectors } from "../../sourceCatalog";
import { isTerminalRunStatus, reportPathFromRun, runIdFromResponse } from "./RunOutputModel";

const CHAT_CONNECTOR_NAMES = new Set(["codex", "hermes", "openclaw", "claude_code", "generic_chat"]);

export function useRunLauncher(context: AppContext, mode: "ingest" | "lint") {
  const [configuredInputScope, setConfiguredInputScope] = useState("");
  const [inputFilePath, setInputFilePath] = useState("");
  const [inputFolderPath, setInputFolderPath] = useState("");
  const [localInputKind, setLocalInputKind] = useState<"file" | "folder">("file");
  const [selectedChatSessionId, setSelectedChatSessionId] = useState("");
  const [lintMode, setLintMode] = useState("deterministic");
  const [trackedRunId, setTrackedRunId] = useState<string | null>(null);
  const [terminalNoticeRunId, setTerminalNoticeRunId] = useState<string | null>(null);
  const configReady = context.configExists;
  const workflowView = mode === "lint" ? "lint" : "ingest";

  const sourceCatalogQuery = useQuery({
    queryKey: queryKeys.sourceCatalog(context.configPath),
    queryFn: () => getSourceCatalog(context.configPath),
    enabled: mode !== "lint",
    staleTime: 60_000,
  });
  const connectorOptions = useMemo(() => sortSourceConnectors(sourceCatalogQuery.data?.connectors || []), [sourceCatalogQuery.data?.connectors]);
  const configuredChatOptions = useMemo(
    () => connectorOptions.filter((connector) => CHAT_CONNECTOR_NAMES.has(connector.name) && connector.enabled),
    [connectorOptions],
  );
  const chatSessionsQuery = useQuery({
    queryKey: queryKeys.runChatSessions(context.activeVaultId),
    queryFn: () => listChatSessions(context.activeVaultSelector, 50),
    enabled: mode !== "lint",
    staleTime: 30_000,
  });
  const chatSessions = chatSessionsQuery.data?.sessions || [];
  const knoarborChatTitle = context.t("knoarborChatConnector");
  const configuredInputOptions = useMemo(
    () => [
      ...(chatSessions.length ? [{ name: "knoarbor_chat", title: knoarborChatTitle }] : []),
      ...configuredChatOptions.map((connector) => ({ name: connector.name, title: connector.name })),
    ],
    [chatSessions.length, configuredChatOptions, knoarborChatTitle],
  );

  useEffect(() => {
    if (selectedChatSessionId && chatSessions.some((session) => session.session_id === selectedChatSessionId)) return;
    setSelectedChatSessionId(chatSessions[0]?.session_id || "");
  }, [chatSessions, selectedChatSessionId]);

  useEffect(() => {
    if (configuredInputScope && configuredInputOptions.some((option) => option.name === configuredInputScope)) return;
    setConfiguredInputScope(configuredInputOptions[0]?.name || "");
  }, [configuredInputOptions, configuredInputScope]);

  useEffect(() => {
    if (!trackedRunId) return;
    const run = [...context.activeRuns, ...context.recentRuns].find((item) => item.run_id === trackedRunId);
    if (!run) return;
    const terminal = isTerminalRunStatus(run.status);
    if (terminal && terminalNoticeRunId === run.run_id) return;
    const reportPath = reportPathFromRun(run);
    context.setNotice({
      message: `${context.t(run.flow)} · ${runStatusLabel(run.status, context.t)}${run.message ? `：${run.message}` : ""}`,
      error: run.status === "failed",
      actionLabel: reportPath ? context.t("openReport") : context.t("viewRun"),
      onAction: reportPath ? () => context.openReport(reportPath) : () => context.navigate(workflowView),
    });
    if (terminal) setTerminalNoticeRunId(run.run_id);
  }, [context, terminalNoticeRunId, trackedRunId]);

  async function runOperation(operation: () => Promise<unknown>) {
    if (!configReady) {
      const message = context.t("configRequired");
      context.setNotice({ message, error: true });
      return;
    }
    try {
      const response = await operation();
      const runId = runIdFromResponse(response);
      if (runId) {
        setTrackedRunId(runId);
        setTerminalNoticeRunId(null);
      }
      context.setNotice({
        message: context.t("runStarted"),
        actionLabel: context.t("viewRun"),
        onAction: () => context.navigate(workflowView),
      });
      await context.loadVaultState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      context.setNotice({ message, error: true });
    }
  }

  async function chooseInputFile() {
    const result = await selectDesktopFile({
      defaultPath: inputFilePath || undefined,
      title: context.t("chooseInputFile"),
    });
    if (!result.canceled && result.path) setInputFilePath(result.path);
  }

  async function chooseInputFolder() {
    const result = await selectDesktopDirectory({
      defaultPath: inputFolderPath || undefined,
      title: context.t("chooseInputFolder"),
    });
    if (!result.canceled && result.path) setInputFolderPath(result.path);
  }

  function startIngest(scope: string) {
    void runOperation(() =>
      scope === "knoarbor_chat"
        ? ingestChatSession(context.activeVaultSelector, selectedChatSessionId)
        : scope === "file"
        ? runIngestFile({
            config_path: context.configPath,
            vault_id: context.activeVaultId,
            input_path: inputFilePath,
            write: true,
            write_report: true,
            append_ledger: true,
          })
        : scope === "folder"
        ? runIngestFolder({
            config_path: context.configPath,
            vault_id: context.activeVaultId,
            input_path: inputFolderPath,
            write: true,
            write_report: true,
            append_ledger: true,
          })
        : runIngest({
            config_path: context.configPath,
            vault_id: context.activeVaultId,
            connector_names: [scope],
            write: true,
            write_report: true,
            append_ledger: true,
          }),
    );
  }

  function startLint() {
    void runOperation(() =>
      runLint({
        config_path: context.configPath,
        vault_id: context.activeVaultId,
        mode: lintMode,
        apply_safe_fixes: true,
        auto_apply_reviewed_changes: true,
        write_report: true,
        append_ledger: true,
        scope: {
          scope_id: `ui:${new Date().toISOString()}`,
          trigger: "manual",
          source: { kind: "ui" },
          changed_pages: [],
          recommended_lint_modes: [lintMode],
          reason: "Manual lint maintenance run from UI.",
        },
      }),
    );
  }

  return {
    canSelectDirectory: canSelectDesktopDirectory(),
    canSelectFile: canSelectDesktopFile(),
    configuredInputOptions,
    configuredInputScope,
    chatSessions,
    chatSessionsLoading: chatSessionsQuery.isLoading,
    chooseInputFile,
    chooseInputFolder,
    configReady,
    inputFilePath,
    inputFolderPath,
    localInputKind,
    lintMode,
    selectedChatSessionId,
    setConfiguredInputScope,
    setInputFilePath,
    setInputFolderPath,
    setLocalInputKind,
    setLintMode,
    setSelectedChatSessionId,
    startIngest,
    startLint,
  };
}
