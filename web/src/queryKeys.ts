export const queryKeys = {
  health: ["health"] as const,
  config: ["config"] as const,
  doctor: (configPath?: string | null) => ["doctor", configPath || "default", "light"] as const,
  status: (vaultPath: string) => ["vault", vaultPath, "status"] as const,
  reports: (vaultPath: string) => ["vault", vaultPath, "reports"] as const,
  activeRuns: (vaultPath: string) => ["vault", vaultPath, "runs", "active"] as const,
  recentRuns: (vaultPath: string) => ["vault", vaultPath, "runs", "recent"] as const,
  graph: (vaultPath: string) => ["vault", vaultPath, "graph"] as const,
  pages: (vaultPath: string) => ["vault", vaultPath, "pages"] as const,
  queryTrends: (vaultPath: string) => ["vault", vaultPath, "query-trends"] as const,
};
