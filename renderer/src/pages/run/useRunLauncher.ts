import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getSourceCatalog, ingestChatSession, listChatSessions, runIngest, runIngestFile, runIngestFolder, runLint } from "../../api/client";
import type { RunAppContext } from "../../appContext";
import { canSelectDesktopDirectory, canSelectDesktopFile, selectDesktopDirectory, selectDesktopFile } from "../../desktop/desktopBridge";
import {
  defaultExcerptTargetVaultId,
  excerptDraftIsValid,
  submitExcerptDraft,
  type ExcerptIngestDraft,
} from "../../ingest/excerptIngest";
import { queryKeys } from "../../queryKeys";
import { sortSourceConnectors } from "../../sourceCatalog";

const CHAT_CONNECTOR_NAMES = new Set(["codex", "hermes", "openclaw", "claude_code", "generic_chat"]);

export type IngestPreparation = {
  inputPath: string;
  kind: "document" | "folder";
};

export function ingestPreparation(scope: string, inputPath: string): IngestPreparation | null {
  const trimmedPath = inputPath.trim();
  if (scope === "folder") return { inputPath: trimmedPath, kind: "folder" };
  if (scope !== "file") return null;
  const extension = trimmedPath.toLowerCase().split(/[?#]/, 1)[0].match(/\.([^.\\/]+)$/)?.[1] || "";
  if (extension === "md" || extension === "markdown") return null;
  return { inputPath: trimmedPath, kind: "document" };
}

export function useRunLauncher(context: RunAppContext, mode: "ingest" | "lint", active = true) {
  const [configuredInputScope, setConfiguredInputScope] = useState("");
  const [inputFilePath, setInputFilePath] = useState("");
  const [inputFolderPath, setInputFolderPath] = useState("");
  const [localInputKind, setLocalInputKind] = useState<"file" | "folder">("file");
  const [selectedChatSessionId, setSelectedChatSessionId] = useState("");
  const [chatIngestOpen, setChatIngestOpen] = useState(false);
  const [chatIngestTitle, setChatIngestTitle] = useState("");
  const [chatIngestTargetVaultId, setChatIngestTargetVaultId] = useState("");
  const [chatIngestSubmitting, setChatIngestSubmitting] = useState(false);
  const [customInputDraft, setCustomInputDraft] = useState<ExcerptIngestDraft | null>(null);
  const [customInputSubmitting, setCustomInputSubmitting] = useState(false);
  const [ingestSubmitting, setIngestSubmitting] = useState(false);
  const [activePreparation, setActivePreparation] = useState<IngestPreparation | null>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const configReady = context.configExists;

  const sourceCatalogQuery = useQuery({
    queryKey: queryKeys.sourceCatalog(context.configPath),
    queryFn: () => getSourceCatalog(context.configPath),
    enabled: active && mode !== "lint",
    refetchOnWindowFocus: active,
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
    enabled: active && mode !== "lint",
    refetchOnWindowFocus: active,
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

  async function runOperation(operation: () => Promise<unknown>): Promise<boolean> {
    setLaunchError(null);
    if (!configReady) {
      setLaunchError(context.t("configRequired"));
      return false;
    }
    try {
      const response = await operation();
      const run = workflowRunIdentity(response);
      if (run) context.watchRunToTerminal(run.runId, run.vaultId);
      await context.loadVaultState();
      return true;
    } catch (error) {
      console.error("Workflow launch failed", error);
      setLaunchError(readableLaunchError(error, context));
      return false;
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

  async function startIngest(scope: string) {
    if (scope === "knoarbor_chat") {
      const session = chatSessions.find((item) => item.session_id === selectedChatSessionId);
      setChatIngestTitle(session?.title || "");
      setChatIngestTargetVaultId(defaultTargetVaultId(context, session?.vault_id ?? undefined));
      setChatIngestOpen(true);
      return;
    }
    const inputPath = scope === "file" ? inputFilePath : scope === "folder" ? inputFolderPath : "";
    setIngestSubmitting(true);
    setActivePreparation(ingestPreparation(scope, inputPath));
    try {
      await runOperation(() =>
        scope === "file"
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
    } finally {
      setIngestSubmitting(false);
      setActivePreparation(null);
    }
  }

  async function confirmChatSessionIngest() {
    const targetVaultId = chatIngestTargetVaultId || defaultTargetVaultId(context);
    const selectedSession = chatSessions.find((session) => session.session_id === selectedChatSessionId);
    if (!selectedSession || !targetVaultId || !chatIngestTitle.trim()) return;
    setChatIngestSubmitting(true);
    try {
      const completed = await runOperation(() =>
        ingestChatSession(context.activeVaultSelector, selectedChatSessionId, {
          expected_session_revision: selectedSession.session_revision,
          source_title: chatIngestTitle.trim(),
          target_vault_id: targetVaultId,
        }),
      );
      if (completed) setChatIngestOpen(false);
    } finally {
      setChatIngestSubmitting(false);
    }
  }

  function openCustomInput() {
    setLaunchError(null);
    setCustomInputDraft({
      content: "",
      context: {
        source_app: "knoarbor",
        input_method: "manual_editor",
      },
      title: "",
      targetVaultId: defaultExcerptTargetVaultId(context),
    });
  }

  function closeCustomInput() {
    setCustomInputDraft(null);
    setLaunchError(null);
  }

  async function confirmCustomInput() {
    if (!excerptDraftIsValid(customInputDraft)) return;
    setCustomInputSubmitting(true);
    try {
      const completed = await runOperation(() => submitExcerptDraft(context.configPath, customInputDraft));
      if (completed) closeCustomInput();
    } finally {
      setCustomInputSubmitting(false);
    }
  }

  function startLint() {
    void runOperation(() =>
      runLint({
        config_path: context.configPath,
        vault_id: context.activeVaultId,
        mode: "semantic",
        write_report: true,
        append_ledger: true,
        scope: {
          scope_id: `ui:${new Date().toISOString()}`,
          trigger: "manual",
          source: { kind: "ui" },
          changed_pages: [],
          recommended_lint_modes: ["semantic"],
          reason: "Manual lint maintenance run from UI.",
        },
      }),
    );
  }

  return {
    canSelectDirectory: canSelectDesktopDirectory(),
    canSelectFile: canSelectDesktopFile(),
    activePreparation,
    chatIngestOpen,
    chatIngestSubmitting,
    chatIngestTargetVaultId,
    chatIngestTitle,
    customInputDraft,
    customInputSubmitting,
    configuredInputOptions,
    configuredInputScope,
    chatSessions,
    chatSessionsLoading: chatSessionsQuery.isLoading,
    chooseInputFile,
    chooseInputFolder,
    confirmCustomInput,
    closeCustomInput,
    configReady,
    inputFilePath,
    inputFolderPath,
    ingestSubmitting,
    localInputKind,
    launchError,
    openCustomInput,
    selectedChatSessionId,
    setConfiguredInputScope,
    setChatIngestOpen,
    setChatIngestTargetVaultId,
    setChatIngestTitle,
    setCustomInputDraft,
    setInputFilePath,
    setInputFolderPath,
    setLocalInputKind,
    setSelectedChatSessionId,
    startIngest,
    confirmChatSessionIngest,
    startLint,
  };
}

export function workflowRunIdentity(value: unknown): { runId: string; vaultId?: string } | null {
  if (!value || typeof value !== "object") return null;
  const response = value as Record<string, unknown>;
  if (typeof response.run_id !== "string" || !response.run_id) return null;
  const run = response.run && typeof response.run === "object"
    ? response.run as Record<string, unknown>
    : null;
  return {
    runId: response.run_id,
    vaultId: typeof run?.vault_id === "string" && run.vault_id ? run.vault_id : undefined,
  };
}

export function readableLaunchError(error: unknown, context: Pick<RunAppContext, "t">): string {
  const rawMessage = error instanceof Error ? error.message : String(error);
  const code = /\[(KA-[A-Z]+-\d+)\]/.exec(rawMessage)?.[1] || "";
  const primaryMessage = rawMessage.split("\nHint:", 1)[0].toLowerCase();
  if (
    code === "KA-CFG-001" ||
    code === "KA-CFG-002" ||
    /provider|model|api key|credential|endpoint|configuration|config/.test(primaryMessage)
  ) {
    return context.t("workflowModelConfigurationError");
  }
  if (code && rawMessage.trim()) {
    return rawMessage;
  }
  return context.t("workflowLaunchError");
}

function defaultTargetVaultId(context: RunAppContext, sourceVaultId?: string): string {
  if (sourceVaultId && sourceVaultId !== "all" && context.vaultOptions.some((vault) => !vault.virtual && vault.id === sourceVaultId)) {
    return sourceVaultId;
  }
  if (context.activeVaultId !== "all" && context.vaultOptions.some((vault) => !vault.virtual && vault.id === context.activeVaultId)) {
    return context.activeVaultId;
  }
  return context.vaultOptions.find((vault) => !vault.virtual)?.id || "";
}
