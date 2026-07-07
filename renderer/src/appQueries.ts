import { useMemo } from "react";
import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query";

import {
  getActiveRuns,
  getConfig,
  getDoctor,
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
import { fetchVaultOverview } from "./appRuntime";
import { queryKeys } from "./queryKeys";
import type { ViewName } from "./types";
import { buildVaultOptions, buildVaultSelector, concreteVaultOptions, resolveActiveVault, resolveConcreteVault } from "./vaultRuntime";

type AppQueriesInput = {
  activeView: ViewName;
  configPath: string | null;
  selectedVaultId: string;
  summary: ConfigSummary;
  t: (key: string) => string;
};

export function useAppQueries({ activeView, configPath, selectedVaultId, summary, t }: AppQueriesInput) {
  const isRunView = activeView === "ingest" || activeView === "lint";
  const needsVaultStatus = activeView === "overview" || activeView === "sources" || activeView === "chat" || activeView === "wiki";
  const needsReports = activeView === "overview" || activeView === "ingest" || activeView === "lint" || activeView === "reports";
  const needsRecentRuns = activeView === "overview" || isRunView;
  const needsVaultOverview = activeView === "overview" || activeView === "reports";
  const shouldPollRuns = activeView === "overview" || isRunView;

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
  const activeVault = useMemo(() => resolveActiveVault(vaultOptions, selectedVaultId, effectiveSummary), [effectiveSummary, selectedVaultId, vaultOptions]);
  const concreteOptions = useMemo(() => concreteVaultOptions(vaultOptions), [vaultOptions]);
  const activeConcreteVault = useMemo(() => resolveConcreteVault(vaultOptions, selectedVaultId, effectiveSummary), [effectiveSummary, selectedVaultId, vaultOptions]);
  const vaultPath = activeConcreteVault.path;
  const activeVaultId = activeVault.id;
  const activeVaultSelector = useMemo(() => buildVaultSelector(effectiveConfigPath, activeConcreteVault), [activeConcreteVault, effectiveConfigPath]);

  const doctorQuery = useQuery({
    queryKey: queryKeys.doctor(effectiveConfigPath),
    queryFn: () => getDoctor(effectiveConfigPath, { checkModelRuntime: false, checkConnectorRuntime: false }),
    enabled: configQuery.isSuccess && activeView === "overview",
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

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

  const vaultOverviewQueries = useQueries({
    queries: concreteOptions.map((vault) => ({
      queryKey: queryKeys.overview(vault.id),
      queryFn: () => fetchVaultOverview(vault, effectiveConfigPath),
      enabled: configQuery.isSuccess && concreteOptions.length > 1 && needsVaultOverview,
      staleTime: 20_000,
      placeholderData: keepPreviousData,
    })),
  });

  const doctorReport = doctorQuery.data || null;
  const status = statusQuery.data || null;
  const graph = graphQuery.data || null;
  const pages = pagesQuery.data?.pages || [];
  const reports = reportsQuery.data?.reports || [];
  const queryTrend = queryTrendQuery.data || null;
  const activeRuns = activeRunsQuery.data?.runs || [];
  const recentRuns = recentRunsQuery.data?.runs || [];
  const modelProviders = modelProvidersQuery.data || null;
  const vaultOverviews = vaultOptions.length > 1
    ? concreteOptions.map((vault, index) => {
      const query = vaultOverviewQueries[index];
      return query?.data || {
        vault,
        status: vault.id === activeVaultId ? status : null,
        activeRuns: vault.id === activeVaultId ? activeRuns : [],
        recentRuns: vault.id === activeVaultId ? recentRuns : [],
        reports: vault.id === activeVaultId ? reports : [],
        error: query?.error instanceof Error ? query.error.message : query?.isError ? t("vaultRefreshFailed") : null,
      };
    })
    : [{
      vault: activeConcreteVault,
      status,
      activeRuns,
      recentRuns,
      reports,
      error: null,
    }];

  return {
    activeConcreteVault,
    activeRuns,
    activeVaultId,
    activeVaultSelector,
    concreteOptions,
    configQuery,
    doctorReport,
    effectiveConfigPath,
    effectiveSummary,
    graph,
    healthQuery,
    modelProviders,
    needsRecentRuns,
    needsReports,
    needsVaultStatus,
    pages,
    queryTrend,
    recentRuns,
    reports,
    shouldPollRuns,
    status,
    vaultOptions,
    vaultOverviews,
    vaultPath,
  };
}
