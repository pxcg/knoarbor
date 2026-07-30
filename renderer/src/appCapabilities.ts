import type { AppContext } from "./appContext";

function selectCapabilities<Keys extends readonly (keyof AppContext)[]>(
  context: AppContext,
  keys: Keys,
): Pick<AppContext, Keys[number]> {
  return Object.fromEntries(keys.map((key) => [key, context[key]])) as Pick<
    AppContext,
    Keys[number]
  >;
}

export const chatCapabilities = (context: AppContext) => selectCapabilities(context, [
  "activeVaultId", "activeVaultSelector", "chatScopeVaultId", "chatScopeVaultSelector",
  "consumeNavigationTarget", "configExists", "configPath", "language",
  "modelProbeResults", "modelProviders", "navigate", "openChatSession", "openReport", "openRun", "openSettings",
  "openWikiPageInVault", "navigationTarget", "refreshAll",
  "selectedChatProvider", "setChatScopeVaultId", "setSelectedChatProvider", "t",
  "vaultOptions", "vaultPath",
] as const);

export const wikiCapabilities = (context: AppContext) => selectCapabilities(context, [
  "activeVaultId", "activeVaultSelector", "consumeNavigationTarget", "language",
  "loadVaultState", "navigate", "navigationTarget", "openChatWithPrompt",
  "openPageInGraph", "openRun", "openWikiPage", "pages", "pagesReady", "setActiveVaultId", "t",
  "vaultOptions", "vaultPath",
] as const);

export const runCapabilities = (context: AppContext) => selectCapabilities(context, [
  "activeRuns", "activeVaultId", "activeVaultSelector", "configExists", "configPath",
  "consumeNavigationTarget", "language", "loadVaultState", "refreshAfterRunTerminal", "navigationTarget", "openReport", "openWikiPage",
  "recentRuns", "reports", "setActiveVaultId", "summary", "t", "vaultOptions", "vaultPath", "watchRunToTerminal",
] as const);

export const queryCapabilities = (context: AppContext) => selectCapabilities(context, [
  "activeVaultId", "activeVaultSelector", "openChatWithPrompt", "openPageInGraph",
  "openWikiPageInVault", "setActiveVaultId", "t", "vaultOptions", "vaultPath",
] as const);

export const graphCapabilities = (context: AppContext) => selectCapabilities(context, [
  "activeVaultSelector", "activeVaultId", "consumeNavigationTarget", "graphReady", "language",
  "navigationTarget", "openWikiPage", "setActiveVaultId", "t", "vaultOptions", "vaultPath",
] as const);

export const reportsCapabilities = (context: AppContext) => selectCapabilities(context, [
  "activeVaultId", "configPath", "consumeNavigationTarget", "language",
  "navigationTarget", "openWikiPage", "openWikiPageInVault", "reports", "reportsReady", "setActiveVaultId", "t",
  "vaultOptions", "vaultPath",
] as const);

export const tokensCapabilities = (context: AppContext) => selectCapabilities(context, [
  "activeVaultId", "setActiveVaultId", "t", "vaultOptions", "vaultPath",
] as const);

export const configCapabilities = (context: AppContext) => selectCapabilities(context, [
  "appearanceMode", "configContent", "configPath", "language", "modelProbeResults",
  "refreshAll", "setAppearanceMode", "setConfigContent", "setConfigExists",
  "setConfigPath", "setLanguage", "setModelProbeResults", "setSummary", "t",
] as const);
