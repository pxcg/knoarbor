import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getSourceCatalog, ingestChatSession, listChatSessions, runIngest, runIngestFile, runIngestFolder, runLint } from "../../api/client";
import type { AppContext } from "../../appContext";
import { runStatusLabel } from "../../components/runStatus";
import { canSelectDesktopDirectory, canSelectDesktopFile, selectDesktopDirectory, selectDesktopFile } from "../../desktop/desktopBridge";
import { queryKeys } from "../../queryKeys";
import { sortSourceConnectors } from "../../sourceCatalog";
import { connectorNames, formatRunOutput, isTerminalRunStatus, reportPathFromRun, runIdFromResponse } from "./RunOutputModel";

export function useRunLauncher(context: AppContext, mode: "both" | "ingest" | "lint") {
  const [connectors, setConnectors] = useState("");
  const [inputFilePath, setInputFilePath] = useState("");
  const [inputFolderPath, setInputFolderPath] = useState("");
  const [inputScope, setInputScope] = useState("enabled");
  const [selectedChatSessionId, setSelectedChatSessionId] = useState("");
  const [lintMode, setLintMode] = useState("deterministic");
  const [runOutput, setRunOutput] = useState(() => context.t("noRunYet"));
  const [trackedRunId, setTrackedRunId] = useState<string | null>(null);
  const [terminalNoticeRunId, setTerminalNoticeRunId] = useState<string | null>(null);
  const configReady = context.configExists;

  const sourceCatalogQuery = useQuery({
    queryKey: queryKeys.sourceCatalog(context.configPath),
    queryFn: () => getSourceCatalog(context.configPath),
    enabled: mode !== "lint",
    staleTime: 60_000,
  });
  const connectorOptions = sortSourceConnectors(sourceCatalogQuery.data?.connectors || []);
  const chatSessionsQuery = useQuery({
    queryKey: queryKeys.runChatSessions(context.activeVaultId),
    queryFn: () => listChatSessions(context.activeVaultSelector, 50),
    enabled: mode !== "lint",
    staleTime: 30_000,
  });
  const chatSessions = chatSessionsQuery.data?.sessions || [];

  useEffect(() => {
    if (selectedChatSessionId && chatSessions.some((session) => session.session_id === selectedChatSessionId)) return;
    setSelectedChatSessionId(chatSessions[0]?.session_id || "");
  }, [chatSessions, selectedChatSessionId]);

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
      actionLabel: reportPath ? context.t("openReport") : context.t("openRuns"),
      onAction: reportPath ? () => context.openReport(reportPath) : () => context.navigate("runs"),
    });
    if (terminal) setTerminalNoticeRunId(run.run_id);
  }, [context, terminalNoticeRunId, trackedRunId]);

  async function runOperation(operation: () => Promise<unknown>) {
    if (!configReady) {
      const message = context.t("configRequired");
      setRunOutput(message);
      context.setNotice({ message, error: true });
      return;
    }
    setRunOutput(context.t("running"));
    try {
      const response = await operation();
      setRunOutput(formatRunOutput(response, context.t));
      const runId = runIdFromResponse(response);
      if (runId) {
        setTrackedRunId(runId);
        setTerminalNoticeRunId(null);
      }
      context.setNotice({
        message: context.t("runStarted"),
        actionLabel: context.t("openRuns"),
        onAction: () => context.navigate("runs"),
      });
      await context.loadVaultState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRunOutput(message);
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

  function startIngest() {
    void runOperation(() =>
      inputScope === "knoarbor_chat"
        ? ingestChatSession(context.activeVaultSelector, selectedChatSessionId)
        : inputScope === "file"
        ? runIngestFile({
            config_path: context.configPath,
            vault_id: context.activeVaultId,
            input_path: inputFilePath,
            write: true,
            write_report: true,
            append_ledger: true,
          })
        : inputScope === "folder"
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
            connector_names: connectorNames(inputScope, connectors),
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
    chatSessions,
    chatSessionsLoading: chatSessionsQuery.isLoading,
    chooseInputFile,
    chooseInputFolder,
    configReady,
    connectorOptions,
    connectors,
    inputFilePath,
    inputFolderPath,
    inputScope,
    lintMode,
    runOutput,
    selectedChatSessionId,
    setConnectors,
    setInputFilePath,
    setInputFolderPath,
    setInputScope,
    setLintMode,
    setRunOutput,
    setSelectedChatSessionId,
    startIngest,
    startLint,
  };
}
