import type { Dispatch, SetStateAction } from "react";

import type {
  ConfigSummary,
  GraphResponse,
  ModelProviderProbeState,
  ModelProvidersResponse,
  PageSummary,
  QueryTrendResponse,
  ReportSummary,
  UiStatusResponse,
  VaultSelector,
} from "./api/client";
import type { AppearanceMode, Language, ViewName } from "./types";
import type { AppNavigationTarget } from "./appNavigation";
import type { RunRecord } from "./types";
import type { VaultOption } from "./vaultRuntime";

export type VaultRefreshScope = {
  status?: boolean;
  reports?: boolean;
  activeRuns?: boolean;
  recentRuns?: boolean;
};

export type AppContext = {
  configPath: string | null;
  configContent: string;
  configExists: boolean;
  graph: GraphResponse | null;
  graphReady: boolean;
  navigationTarget: AppNavigationTarget | null;
  consumeNavigationTarget: (requestId: number) => void;
  healthHint: string;
  pages: PageSummary[];
  pagesReady: boolean;
  queryTrend: QueryTrendResponse | null;
  activeRuns: RunRecord[];
  recentRuns: RunRecord[];
  reports: ReportSummary[];
  reportsReady: boolean;
  serviceOnline: boolean | null;
  modelProviders: ModelProvidersResponse | null;
  modelProbeResults: Record<string, ModelProviderProbeState>;
  selectedChatProvider: string;
  setModelProbeResults: Dispatch<SetStateAction<Record<string, ModelProviderProbeState>>>;
  setSelectedChatProvider: (provider: string) => void;
  setConfigContent: Dispatch<SetStateAction<string>>;
  setConfigPath: Dispatch<SetStateAction<string | null>>;
  setConfigExists: Dispatch<SetStateAction<boolean>>;
  setQueryTrend: Dispatch<SetStateAction<QueryTrendResponse | null>>;
  setActiveRuns: Dispatch<SetStateAction<RunRecord[]>>;
  setRecentRuns: Dispatch<SetStateAction<RunRecord[]>>;
  setSummary: Dispatch<SetStateAction<ConfigSummary>>;
  setStatus: Dispatch<SetStateAction<UiStatusResponse | null>>;
  setGraph: Dispatch<SetStateAction<GraphResponse | null>>;
  setPages: Dispatch<SetStateAction<PageSummary[]>>;
  setReports: Dispatch<SetStateAction<ReportSummary[]>>;
  navigate: (view: ViewName) => void;
  openPageInGraph: (pageId: string, vaultId?: string) => void;
  openWikiPage: (path: string) => void;
  openWikiPageInVault: (vaultId: string | null | undefined, path: string) => void;
  openChatWithPrompt: (prompt: string, vaultId?: string | null) => void;
  openChatSession: (sessionId: string | null, vaultId?: string | null) => void;
  openReport: (path: string, vaultId?: string) => void;
  openRun: (runId: string, vaultId: string, flow: RunRecord["flow"]) => void;
  openSettings: () => void;
  status: UiStatusResponse | null;
  summary: ConfigSummary;
  activeVaultId: string;
  activeVaultSelector: VaultSelector;
  chatScopeVaultId: string;
  chatScopeVaultSelector: VaultSelector;
  vaultOptions: VaultOption[];
  setActiveVaultId: (vaultId: string) => void;
  setChatScopeVaultId: (vaultId: string) => void;
  vaultPath: string;
  refreshAll: () => Promise<boolean>;
  loadVaultState: (vault?: VaultOption, scope?: VaultRefreshScope) => Promise<void>;
  refreshAfterRunTerminal: (run: RunRecord) => Promise<void>;
  watchRunToTerminal: (runId: string, vaultId?: string | null) => void;
  language: Language;
  setLanguage: (language: Language) => void;
  appearanceMode: AppearanceMode;
  setAppearanceMode: (mode: AppearanceMode) => void;
  t: (key: string) => string;
};

type AppContextSlice<Keys extends keyof AppContext> = Pick<AppContext, Keys>;

export type LocalizationContext = AppContextSlice<"language" | "t">;

export type WikiAppContext = AppContextSlice<
  | "activeVaultId"
  | "activeVaultSelector"
  | "consumeNavigationTarget"
  | "language"
  | "loadVaultState"
  | "navigate"
  | "navigationTarget"
  | "openChatWithPrompt"
  | "openPageInGraph"
  | "openRun"
  | "openWikiPage"
  | "pages"
  | "pagesReady"
  | "setActiveVaultId"
  | "t"
  | "vaultOptions"
  | "vaultPath"
>;

export type QueryAppContext = AppContextSlice<
  | "activeVaultId"
  | "activeVaultSelector"
  | "openChatWithPrompt"
  | "openPageInGraph"
  | "openWikiPageInVault"
  | "setActiveVaultId"
  | "t"
  | "vaultOptions"
  | "vaultPath"
>;

export type ChatAppContext = AppContextSlice<
  | "activeVaultId"
  | "activeVaultSelector"
  | "chatScopeVaultId"
  | "chatScopeVaultSelector"
  | "consumeNavigationTarget"
  | "configExists"
  | "configPath"
  | "language"
  | "modelProbeResults"
  | "modelProviders"
  | "navigate"
  | "openChatSession"
  | "openReport"
  | "openRun"
  | "openSettings"
  | "openWikiPageInVault"
  | "navigationTarget"
  | "refreshAll"
  | "selectedChatProvider"
  | "setChatScopeVaultId"
  | "setSelectedChatProvider"
  | "t"
  | "vaultOptions"
  | "vaultPath"
>;

export type RunAppContext = AppContextSlice<
  | "activeRuns"
  | "activeVaultId"
  | "activeVaultSelector"
  | "configExists"
  | "configPath"
  | "language"
  | "loadVaultState"
  | "refreshAfterRunTerminal"
  | "watchRunToTerminal"
  | "consumeNavigationTarget"
  | "navigationTarget"
  | "openReport"
  | "openWikiPage"
  | "recentRuns"
  | "reports"
  | "summary"
  | "setActiveVaultId"
  | "t"
  | "vaultOptions"
  | "vaultPath"
>;

export type ConfigAppContext = AppContextSlice<
  | "appearanceMode"
  | "configContent"
  | "configPath"
  | "language"
  | "modelProbeResults"
  | "refreshAll"
  | "setAppearanceMode"
  | "setConfigContent"
  | "setConfigExists"
  | "setConfigPath"
  | "setLanguage"
  | "setModelProbeResults"
  | "setSummary"
  | "t"
>;

export type ReportsAppContext = AppContextSlice<
  | "activeVaultId"
  | "configPath"
  | "consumeNavigationTarget"
  | "language"
  | "navigationTarget"
  | "openWikiPage"
  | "openWikiPageInVault"
  | "reports"
  | "reportsReady"
  | "setActiveVaultId"
  | "t"
  | "vaultOptions"
  | "vaultPath"
>;

export type GraphAppContext = AppContextSlice<
  "activeVaultSelector" | "activeVaultId" | "consumeNavigationTarget" | "graphReady" | "language" | "navigationTarget" | "openWikiPage" | "setActiveVaultId" | "t" | "vaultOptions" | "vaultPath"
>;

export type TokensAppContext = AppContextSlice<"activeVaultId" | "setActiveVaultId" | "t" | "vaultOptions" | "vaultPath">;

export type SidebarAppContext = AppContextSlice<
  | "activeVaultId"
  | "configExists"
  | "configPath"
  | "language"
  | "navigate"
  | "openChatSession"
  | "openRun"
  | "refreshAll"
  | "t"
  | "vaultOptions"
>;

export type ExcerptIngestAppContext = AppContextSlice<
  "activeVaultId" | "t" | "vaultOptions"
>;

export type ChatIngestTargetContext = AppContextSlice<
  "language" | "t" | "vaultOptions"
>;
