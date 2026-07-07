import type { Dispatch, SetStateAction } from "react";

import type {
  ConfigSummary,
  DoctorReport,
  GraphResponse,
  ModelProviderProbeState,
  ModelProvidersResponse,
  PageSummary,
  QueryResult,
  QueryTrendResponse,
  ReportSummary,
  UiStatusResponse,
  VaultSelector,
} from "./api/client";
import type { Language, ViewName } from "./types";
import type { RunRecord } from "./types";
import type { VaultOption, VaultOverview } from "./vaultRuntime";

export type AppNotice = {
  message: string;
  error?: boolean;
  actionLabel?: string;
  onAction?: () => void;
};

export type PendingChatSessionRequest = {
  sessionId: string | null;
  vaultId?: string | null;
  requestId: number;
};

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
  doctorReport: DoctorReport | null;
  graph: GraphResponse | null;
  focusedPageId: string | null;
  focusedWikiPath: string | null;
  focusedReportPath: string | null;
  pendingChatPrompt: string;
  pendingChatSessionRequest: PendingChatSessionRequest | null;
  healthHint: string;
  pages: PageSummary[];
  queryResults: QueryResult[];
  queryContextPack: string;
  queryTrend: QueryTrendResponse | null;
  activeRuns: RunRecord[];
  recentRuns: RunRecord[];
  reports: ReportSummary[];
  serviceOnline: boolean | null;
  modelProviders: ModelProvidersResponse | null;
  modelProbeResults: Record<string, ModelProviderProbeState>;
  selectedChatProvider: string;
  setModelProbeResults: Dispatch<SetStateAction<Record<string, ModelProviderProbeState>>>;
  setSelectedChatProvider: (provider: string) => void;
  setConfigContent: Dispatch<SetStateAction<string>>;
  setConfigPath: Dispatch<SetStateAction<string | null>>;
  setConfigExists: Dispatch<SetStateAction<boolean>>;
  setDoctorReport: Dispatch<SetStateAction<DoctorReport | null>>;
  setNotice: Dispatch<SetStateAction<AppNotice | null>>;
  setQueryResults: Dispatch<SetStateAction<QueryResult[]>>;
  setQueryContextPack: Dispatch<SetStateAction<string>>;
  setQueryTrend: Dispatch<SetStateAction<QueryTrendResponse | null>>;
  setActiveRuns: Dispatch<SetStateAction<RunRecord[]>>;
  setRecentRuns: Dispatch<SetStateAction<RunRecord[]>>;
  setSummary: Dispatch<SetStateAction<ConfigSummary>>;
  setStatus: Dispatch<SetStateAction<UiStatusResponse | null>>;
  setGraph: Dispatch<SetStateAction<GraphResponse | null>>;
  setPages: Dispatch<SetStateAction<PageSummary[]>>;
  setReports: Dispatch<SetStateAction<ReportSummary[]>>;
  navigate: (view: ViewName) => void;
  openPageInGraph: (pageId: string) => void;
  openWikiPage: (path: string) => void;
  openWikiPageInVault: (vaultId: string | null | undefined, path: string) => void;
  openChatWithPrompt: (prompt: string, vaultId?: string | null) => void;
  clearPendingChatPrompt: () => void;
  openChatSession: (sessionId: string | null, vaultId?: string | null) => void;
  clearPendingChatSessionRequest: () => void;
  openReport: (path: string) => void;
  openSettings: () => void;
  status: UiStatusResponse | null;
  summary: ConfigSummary;
  activeVaultId: string;
  activeVaultSelector: VaultSelector;
  vaultOptions: VaultOption[];
  vaultOverviews: VaultOverview[];
  setActiveVaultId: (vaultId: string) => void;
  vaultPath: string;
  refreshAll: () => Promise<boolean>;
  loadVaultState: (vault?: VaultOption, scope?: VaultRefreshScope) => Promise<void>;
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
};
