import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

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
} from "./api/client";
import type { AppNotice, VaultRefreshScope } from "./appContext";
import { queryKeys } from "./queryKeys";
import type { ViewName } from "./types";
import { buildVaultOptions, buildVaultSelector, resolveConcreteVault, type VaultOption } from "./vaultRuntime";

type AppRefreshInput = {
  activeConcreteVault: VaultOption;
  activeView: ViewName;
  effectiveConfigPath: string | null;
  needsRecentRuns: boolean;
  needsReports: boolean;
  needsVaultStatus: boolean;
  selectedVaultId: string;
  setNotice: (notice: AppNotice | null) => void;
  shouldPollRuns: boolean;
  t: (key: string) => string;
};

export function useAppRefresh({
  activeConcreteVault,
  activeView,
  effectiveConfigPath,
  needsRecentRuns,
  needsReports,
  needsVaultStatus,
  selectedVaultId,
  setNotice,
  shouldPollRuns,
  t,
}: AppRefreshInput) {
  const queryClient = useQueryClient();

  const loadVaultState = useCallback(async (vault: VaultOption = activeConcreteVault, scope: VaultRefreshScope = {}) => {
    const normalizedScope = {
      status: scope.status ?? true,
      reports: scope.reports ?? true,
      activeRuns: scope.activeRuns ?? true,
      recentRuns: scope.recentRuns ?? true,
    };
    const tasks: Promise<unknown>[] = [];
    if (normalizedScope.status) tasks.push(queryClient.fetchQuery({ queryKey: queryKeys.status(vault.id), queryFn: () => getStatus(vault.path), staleTime: 0 }));
    const selector = buildVaultSelector(effectiveConfigPath, vault);
    if (normalizedScope.reports) tasks.push(queryClient.fetchQuery({ queryKey: queryKeys.reports(vault.id), queryFn: () => getReports(selector), staleTime: 0 }));
    if (normalizedScope.activeRuns) tasks.push(queryClient.fetchQuery({ queryKey: queryKeys.activeRuns(vault.id), queryFn: () => getActiveRuns(selector), staleTime: 0 }));
    if (normalizedScope.recentRuns) tasks.push(queryClient.fetchQuery({ queryKey: queryKeys.recentRuns(vault.id), queryFn: () => getRuns(selector, false, 12), staleTime: 0 }));
    const results = await Promise.allSettled(tasks);
    const failure = results.find((result) => result.status === "rejected");
    if (failure?.status === "rejected") {
      const reason = failure.reason || t("vaultRefreshFailed");
      setNotice({ message: reason instanceof Error ? reason.message : String(reason), error: true });
    }
  }, [activeConcreteVault, effectiveConfigPath, queryClient, setNotice, t]);

  const refreshAll = useCallback(async () => {
    setNotice(null);
    try {
      const configResult = await queryClient.fetchQuery({ queryKey: queryKeys.config, queryFn: getConfig });
      const nextRegistry = await queryClient.fetchQuery({
        queryKey: queryKeys.vaults(configResult.config_path),
        queryFn: () => getVaults(configResult.config_path),
      });
      const nextVaultOptions = buildVaultOptions(configResult.summary || {}, nextRegistry);
      const nextVault = resolveConcreteVault(nextVaultOptions, selectedVaultId, configResult.summary || {});
      const nextSelector = buildVaultSelector(configResult.config_path, nextVault);
      const refreshTasks: Promise<unknown>[] = [
        queryClient.fetchQuery({ queryKey: queryKeys.health, queryFn: getHealth, staleTime: 0 }),
      ];
      if (activeView === "overview") {
        refreshTasks.push(queryClient.fetchQuery({
          queryKey: queryKeys.doctor(configResult.config_path),
          queryFn: () => getDoctor(configResult.config_path, { checkModelRuntime: false, checkConnectorRuntime: false }),
          staleTime: 0,
        }));
      }
      if (needsVaultStatus || needsReports || needsRecentRuns || shouldPollRuns) {
        refreshTasks.push(loadVaultState(nextVault, {
          status: needsVaultStatus,
          reports: needsReports,
          activeRuns: shouldPollRuns,
          recentRuns: needsRecentRuns,
        }));
      }
      if (activeView === "graph") {
        refreshTasks.push(queryClient.fetchQuery({ queryKey: queryKeys.graph(nextVault.id), queryFn: () => getGraph(nextVault.path), staleTime: 0 }));
      }
      if (activeView === "wiki") {
        refreshTasks.push(queryClient.fetchQuery({ queryKey: queryKeys.pages(nextVault.id), queryFn: () => getPages(nextSelector), staleTime: 0 }));
      }
      if (activeView === "query") {
        refreshTasks.push(queryClient.fetchQuery({ queryKey: queryKeys.queryTrends(nextVault.id), queryFn: () => getQueryTrends(nextSelector), staleTime: 0 }));
      }
      if (activeView === "chat" || activeView === "settings") {
        refreshTasks.push(queryClient.fetchQuery({
          queryKey: queryKeys.modelProviders(configResult.config_path),
          queryFn: () => getModelProviders(configResult.config_path),
          staleTime: 0,
        }));
      }
      await Promise.all(refreshTasks);
      return true;
    } catch (error) {
      setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      return false;
    }
  }, [activeView, loadVaultState, needsRecentRuns, needsReports, needsVaultStatus, queryClient, selectedVaultId, setNotice, shouldPollRuns]);

  return { loadVaultState, refreshAll };
}
