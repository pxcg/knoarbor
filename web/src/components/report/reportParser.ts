export type ReportMetric = {
  key: string;
  value: string;
};

export type ReportSection = {
  title: string;
  items: Array<{ key?: string; value: string }>;
};

export type ReportChange = {
  page: string;
  action?: string;
  summary?: string;
  diff: string[];
};

export type PageArtifact = {
  path: string;
  changes: ReportChange[];
};

export function parseReportRunId(content: string): string | null {
  const match = content.match(/^- run_id:\s*(.+)$/m);
  return match?.[1]?.trim() || null;
}

export function parseReport(content: string): { metrics: ReportMetric[]; sections: ReportSection[] } {
  const lines = content.split(/\r?\n/);
  const metrics: ReportMetric[] = [];
  const sections: ReportSection[] = [];
  let currentSection: ReportSection | null = null;
  let inFence = false;

  for (const line of lines) {
    if (line.startsWith("```")) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) {
      currentSection = { title: heading[1].trim(), items: [] };
      sections.push(currentSection);
      continue;
    }
    const structured = line.match(/^-\s+(.+)$/);
    if (structured && currentSection && isStructuredReportLine(structured[1])) {
      currentSection.items.push({ value: structured[1].trim() });
      continue;
    }
    const bullet = line.match(/^-\s+([^:]+):\s*(.*)$/);
    if (bullet) {
      const item = { key: bullet[1].trim(), value: bullet[2].trim() || "-" };
      if (currentSection) currentSection.items.push(item);
      else metrics.push(item);
      continue;
    }
    const sectionBullet = line.match(/^-\s+(.+)$/);
    if (sectionBullet && currentSection) currentSection.items.push({ value: sectionBullet[1].trim() });
  }

  return {
    metrics: metrics.slice(0, 18),
    sections: sections
      .map((section) => ({ ...section, items: section.items.slice(0, 8) }))
      .filter((section) => section.items.length)
      .slice(0, 8),
  };
}

export function parseReportArtifacts(content: string): { pages: string[]; changes: ReportChange[] } {
  const lines = content.split(/\r?\n/);
  const pages = new Set<string>();
  const changes: ReportChange[] = [];
  let activeChange: ReportChange | null = null;
  let inDiff = false;
  let collectGeneratedPages = false;

  for (const line of lines) {
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) {
      collectGeneratedPages = false;
    }
    if (/^Generated pages:\s*$/.test(line) || /^##\s+(Generated pages|Written pages|Page Changes)\s*$/i.test(line)) {
      collectGeneratedPages = true;
      continue;
    }
    if (collectGeneratedPages && /^[A-Z][A-Za-z\s]+:\s*$/.test(line) && !/^Generated pages:\s*$/.test(line)) {
      collectGeneratedPages = false;
    }
    const change = line.match(/page_change:\s+`([^`]+)`\s+action=([^\s]+)(?:\s+sections=(.+))?/);
    const lintChange = line.match(/^-\s+`?((?:sources|entities|concepts|comparisons|queries|workflows)\/[^`\s]+?\.md)`?\s+action=([^\s]+)(?:\s+sections=(.+))?/);
    const matchedChange = change || lintChange;
    if (matchedChange) {
      const summary = matchedChange[3]?.trim();
      activeChange = { page: matchedChange[1], action: matchedChange[2], summary: summary && summary !== "none" ? summary : undefined, diff: [] };
      changes.push(activeChange);
      pages.add(matchedChange[1]);
      continue;
    }
    if (collectGeneratedPages) {
      for (const path of extractWikiPagePaths(line)) pages.add(path);
    }
    if (line.startsWith("```diff")) {
      inDiff = true;
      if (!activeChange) activeChange = null;
      continue;
    }
    if (inDiff && line.startsWith("```")) {
      inDiff = false;
      continue;
    }
    if (inDiff && activeChange) activeChange.diff.push(line);
  }

  return { pages: [...pages], changes };
}

export function buildPageArtifacts(pages: string[], changes: ReportChange[]): PageArtifact[] {
  const byPath = new Map<string, ReportChange[]>();
  for (const path of pages) byPath.set(path, []);
  for (const change of changes) {
    const existing = byPath.get(change.page) || [];
    existing.push(change);
    byPath.set(change.page, existing);
  }
  return [...byPath.entries()].map(([path, pageChanges]) => ({ path, changes: pageChanges }));
}

export function getReportMetricNumber(content: string, key: string): number {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = content.match(new RegExp(`^- ${escaped}:\\s*(\\d+)\\s*$`, "m"));
  return match ? Number(match[1]) : 0;
}

export function extractWikiPagePaths(value: string): string[] {
  const paths = new Set<string>();
  for (const match of value.matchAll(/\b(?:sources|entities|concepts|comparisons|queries|workflows)\/[^\s,`]+?\.md\b/g)) {
    paths.add(match[0].replace(/[.)\]}]+$/, ""));
  }
  return [...paths];
}

export function pageName(path: string): string {
  return path.split("/").pop()?.replace(/\.md$/, "") || path;
}

function isStructuredReportLine(value: string): boolean {
  return (
    /^\[\w+]\s+`[^`]+`\s+in\s+`[^`]+`:\s+/.test(value) ||
    /^`[^`]+`\s+\S+\s+\S+\s+->\s+/.test(value) ||
    /^\[(approve|reject)]\s+operation\s+\d+\s+\S+\s+risk=\w+:\s+/.test(value) ||
    /^\[\w+]\s+`[^`]+`\s+on\s+`[^`]+`\s+risk=\w+:\s+/.test(value)
  );
}
