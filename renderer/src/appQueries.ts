import { useMemo } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  getActiveRuns,
  getConfig,
  getGraph,
  getHealth,
  getModelProviders,
  getPages,
  getQueryTrends,
  getReports,
  getRuns,
  getStatus,
  getVaults,
  type ConfigSummary,
} from "./api/client";
import { queryKeys } from "./queryKeys";
import type { ViewName } from "./types";
import { buildVaultOptions, buildVaultSelector, resolveConcreteVault } from "./vaultRuntime";

type AppQueriesInput = {
  activeView: ViewName;
  configPath: string | null;
  selectedVaultId: string;
  summary: ConfigSummary;
};

export function useAppQueries({ activeView, configPath, selectedVaultId, summary }: AppQueriesInput) {
  const isRunView = activeView === "ingest" || activeView === "lint";
  const needsVaultStatus = activeView === "chat" || activeView === "wiki";
  const needsReports = activeView === "ingest" || activeView === "lint" || activeView === "reports";
  const needsRecentRuns = isRunView;
  const shouldPollRuns = isRunView;

  const healthQuery = useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const configQuery = useQuery({
    queryKey: queryKeys.config,
    queryFn: getConfig,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const effectiveConfigPath = configQuery.data?.config_path ?? configPath;
  const effectiveSummary = configQuery.data?.summary || summary;
  const modelProvidersQuery = useQuery({
    queryKey: queryKeys.modelProviders(effectiveConfigPath),
    queryFn: () => getModelProviders(effectiveConfigPath),
    enabled: configQuery.isSuccess,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
  const vaultsQuery = useQuery({
    queryKey: queryKeys.vaults(effectiveConfigPath),
    queryFn: () => getVaults(effectiveConfigPath),
    enabled: configQuery.isSuccess,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
  const vaultOptions = useMemo(() => buildVaultOptions(effectiveSummary, vaultsQuery.data), [effectiveSummary, vaultsQuery.data]);
  const activeVault = useMemo(() => resolveConcreteVault(vaultOptions, selectedVaultId, effectiveSummary), [effectiveSummary, selectedVaultId, vaultOptions]);
  const activeConcreteVault = useMemo(() => resolveConcreteVault(vaultOptions, selectedVaultId, effectiveSummary), [effectiveSummary, selectedVaultId, vaultOptions]);
  const vaultPath = activeConcreteVault.path;
  const activeVaultId = activeVault.id;
  const activeVaultSelector = useMemo(() => buildVaultSelector(effectiveConfigPath, activeConcreteVault), [activeConcreteVault, effectiveConfigPath]);

  const statusQuery = useQuery({
    queryKey: queryKeys.status(activeVaultId),
    queryFn: () => getStatus(vaultPath),
    enabled: configQuery.isSuccess && Boolean(vaultPath) && needsVaultStatus,
    staleTime: 20_000,
    placeholderData: keepPreviousData,
  });

  const reportsQuery = useQuery({
    queryKey: queryKeys.reports(activeVaultId),
    queryFn: () => getReports(activeVaultSelector),
    enabled: configQuery.isSuccess && Boolean(vaultPath) && needsReports,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const activeRunsQuery = useQuery({
    queryKey: queryKeys.activeRuns(activeVaultId),
    queryFn: () => getActiveRuns(activeVaultSelector),
    enabled: configQuery.isSuccess && Boolean(vaultPath),
    refetchInterval: (query) => {
      const runs = query.state.data?.runs || [];
      return shouldPollRuns || runs.length > 0 ? 2500 : false;
    },
    staleTime: 1500,
    placeholderData: keepPreviousData,
  });

  const recentRunsQuery = useQuery({
    queryKey: queryKeys.recentRuns(activeVaultId),
    queryFn: () => getRuns(activeVaultSelector, false, 12),
    enabled: configQuery.isSuccess && Boolean(vaultPath) && needsRecentRuns,
    staleTime: 20_000,
    placeholderData: keepPreviousData,
  });

  const graphQuery = useQuery({
    queryKey: queryKeys.graph(activeVaultId),
    queryFn: () => getGraph(vaultPath),
    enabled: configQuery.isSuccess && activeView === "graph",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const pagesQuery = useQuery({
    queryKey: queryKeys.pages(activeVaultId),
    queryFn: () => getPages(activeVaultSelector),
    enabled: configQuery.isSuccess && activeView === "wiki",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const queryTrendQuery = useQuery({
    queryKey: queryKeys.queryTrends(activeVaultId),
    queryFn: () => getQueryTrends(activeVaultSelector),
    enabled: configQuery.isSuccess && activeView === "query",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const status = statusQuery.data || null;
  const graph = graphQuery.data || null;
  const pages = pagesQuery.data?.pages || [];
  const reports = reportsQuery.data?.reports || [];
  const queryTrend = queryTrendQuery.data || null;
  const activeRuns = activeRunsQuery.data?.runs || [];
  const recentRuns = recentRunsQuery.data?.runs || [];
  const modelProviders = modelProvidersQuery.data || null;
  return {
    activeConcreteVault,
    activeRuns,
    activeVaultId,
    activeVaultSelector,
    configQuery,
    effectiveConfigPath,
    effectiveSummary,
    graph,
    graphReady: graphQuery.isSuccess && !graphQuery.isPlaceholderData && !graphQuery.isFetching,
    healthQuery,
    modelProviders,
    needsRecentRuns,
    needsReports,
    needsVaultStatus,
    pages,
    pagesReady: pagesQuery.isSuccess && !pagesQuery.isPlaceholderData && !pagesQuery.isFetching,
    queryTrend,
    recentRuns,
    reports,
    reportsReady: reportsQuery.isSuccess && !reportsQuery.isPlaceholderData && !reportsQuery.isFetching,
    shouldPollRuns,
    status,
    vaultOptions,
    vaultRegistryReady: vaultsQuery.isSuccess,
    vaultPath,
  };
}
