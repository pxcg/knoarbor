import {
  BookOpen,
  Bot,
  Boxes,
  Braces,
  Activity,
  CheckCheck,
  CircleHelp,
  FileBarChart,
  FileCode2,
  FileText,
  FolderOpen,
  GitFork,
  Hammer,
  type LucideIcon,
  Network,
  PanelTop,
  Search,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";

export type IconName =
  | "overview"
  | "runs"
  | "sources"
  | "wiki"
  | "ingest"
  | "lint"
  | "query"
  | "graph"
  | "reports"
  | "settings"
  | "docs"
  | "github"
  | "markdown"
  | "codex"
  | "hermes"
  | "openclaw"
  | "claude_code"
  | "mineru";

const iconMap: Record<Exclude<IconName, "github">, LucideIcon> = {
  overview: PanelTop,
  runs: Activity,
  sources: Boxes,
  wiki: FolderOpen,
  ingest: GitFork,
  lint: CheckCheck,
  query: Search,
  graph: Network,
  reports: FileBarChart,
  settings: SlidersHorizontal,
  docs: BookOpen,
  markdown: FileText,
  codex: Braces,
  hermes: Bot,
  openclaw: Sparkles,
  claude_code: FileCode2,
  mineru: Hammer,
};

export function LineIcon({ name, className }: { name: IconName; className?: string }) {
  if (name === "github") return <GitHubLogo className={className} />;
  const Icon = iconMap[name] || CircleHelp;
  return <Icon className={className} aria-hidden="true" focusable="false" />;
}

function GitHubLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 3a9 9 0 0 0-3 17c.45.08.62-.2.62-.43v-1.5c-2.54.55-3.07-1.08-3.07-1.08-.42-1.06-1.02-1.34-1.02-1.34-.84-.57.06-.56.06-.56.92.06 1.4.95 1.4.95.82 1.4 2.15 1 2.67.76.08-.6.32-1 .58-1.23-2.03-.23-4.17-1.01-4.17-4.52 0-1 .36-1.82.95-2.46-.1-.23-.41-1.17.09-2.43 0 0 .77-.25 2.53.94A8.8 8.8 0 0 1 12 5.8c.78 0 1.56.1 2.3.31 1.75-1.19 2.52-.94 2.52-.94.5 1.26.19 2.2.09 2.43.59.64.95 1.46.95 2.46 0 3.52-2.14 4.29-4.18 4.52.33.28.62.83.62 1.68v2.49c0 .24.16.52.63.43A9 9 0 0 0 12 3z" />
    </svg>
  );
}
