// Generated from src/knoarbor/product_manifest.json (sha256:7567bdaac86bf266063cbf22786718a54b2692e13e7ba5ad0f80fb5cc4037709).
export const desktopProduct = {
  appDataDir: "KnoArbor",
  appId: "ai.knoarbor.desktop",
  appUserModelId: "ai.knoarbor.desktop",
  defaultVaultName: "KnoArbor",
  envPrefix: "KNOARBOR",
  helpUrl: "https://github.com/pxcg/knoarbor",
  name: "KnoArbor",
  rendererHost: "renderer",
  rendererScheme: "knoarbor",
  supportsUpdates: false,
} as const;

export function productEnvName(name: string): string {
  return `${desktopProduct.envPrefix}_${name}`;
}

export function productEnv(name: string): string | undefined {
  return process.env[productEnvName(name)]?.trim() || undefined;
}
