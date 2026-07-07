import { pathBaseName } from "../../pathUtils";

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
  kind: "changed" | "written" | "related";
};

export type ReportFailure = {
  source?: string;
  stage?: string;
  code?: string;
  message: string;
};

export type ReportArtifacts = {
  changedPages: PageArtifact[];
  writtenPages: PageArtifact[];
  relatedPages: PageArtifact[];
  failures: ReportFailure[];
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

export function parseReportArtifacts(content: string): ReportArtifacts {
  const lines = content.split(/\r?\n/);
  const writtenPages = new Set<string>();
  const relatedPages = new Set<string>();
  const changes: ReportChange[] = [];
  const failures: ReportFailure[] = [];
  let activeChange: ReportChange | null = null;
  let inDiff = false;
  let collectPages: "written" | "related" | null = null;
  let currentSection = "";
  let currentSource = "";
  let currentFailure: ReportFailure | null = null;

  for (const line of lines) {
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) {
      currentSection = heading[1].trim();
      collectPages = null;
      currentSource = "";
      currentFailure = null;
      continue;
    }
    const sourceHeading = line.match(/^###\s+(.+)$/);
    if (sourceHeading) {
      currentSource = sourceHeading[1].trim();
      currentFailure = null;
    }
    if (/^Generated pages:\s*$/.test(line) || /^##\s+(Generated pages|Written pages)\s*$/i.test(line)) {
      collectPages = "written";
      continue;
    }
    if (/^Scoped lint pages:\s*$/.test(line)) {
      collectPages = "related";
      continue;
    }
    if (collectPages && /^[A-Z][A-Za-z\s]+:\s*$/.test(line) && !/^Generated pages:\s*$/.test(line)) {
      collectPages = null;
    }
    const change = line.match(/page_change:\s+`([^`]+)`\s+action=([^\s]+)(?:\s+sections=(.+))?/);
    const lintChange = line.match(/^-\s+`?((?:sources\/)?[^`\s]+?\.md)`?\s+action=([^\s]+)(?:\s+sections=(.+))?/);
    const matchedChange = change || lintChange;
    if (matchedChange) {
      const summary = matchedChange[3]?.trim();
      activeChange = { page: matchedChange[1], action: matchedChange[2], summary: summary && summary !== "none" ? summary : undefined, diff: [] };
      changes.push(activeChange);
      writtenPages.delete(matchedChange[1]);
      relatedPages.delete(matchedChange[1]);
      continue;
    }
    if (collectPages) {
      for (const path of extractWikiPagePaths(line)) {
        if (collectPages === "written") writtenPages.add(path);
        else relatedPages.add(path);
      }
    }
    const wrotePage = line.match(/^-\s+wrote\s+`([^`]+)`/);
    if (wrotePage) writtenPages.add(wrotePage[1]);
    const status = line.match(/^-\s+status:\s*(.+)$/);
    if (status && status[1].trim().toLowerCase() === "failed") {
      currentFailure = { source: currentSource || undefined, message: "failed" };
      failures.push(currentFailure);
    }
    const failureField = line.match(/^-\s+(error_stage|error_code|error_type|error_message):\s*(.+)$/);
    if (failureField) {
      if (!currentFailure) {
        currentFailure = { source: currentSource || undefined, message: "" };
        failures.push(currentFailure);
      }
      if (failureField[1] === "error_stage" || failureField[1] === "error_type") currentFailure.stage = failureField[2].trim();
      if (failureField[1] === "error_code") currentFailure.code = failureField[2].trim();
      if (failureField[1] === "error_message") currentFailure.message = failureField[2].trim();
    }
    if (currentSection === "Recovery Candidates") {
      const recovery = line.match(/^-\s+`([^`]+)`.*?:\s*(.+)$/);
      if (recovery) failures.push({ source: recovery[1], message: recovery[2].trim() });
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

  const changedPageArtifacts = buildPageArtifacts(
    [...new Set(changes.map((change) => change.page))],
    changes,
    "changed",
  );
  return {
    changedPages: changedPageArtifacts,
    writtenPages: buildPageArtifacts([...writtenPages].filter((path) => !changes.some((change) => change.page === path)), changes, "written"),
    relatedPages: buildPageArtifacts([...relatedPages].filter((path) => !writtenPages.has(path) && !changes.some((change) => change.page === path)), changes, "related"),
    failures: failures.filter((failure) => failure.message && failure.message !== "None."),
  };
}

export function buildPageArtifacts(pages: string[], changes: ReportChange[], kind: PageArtifact["kind"] = "related"): PageArtifact[] {
  const byPath = new Map<string, ReportChange[]>();
  for (const path of pages) byPath.set(path, []);
  for (const change of changes) {
    const existing = byPath.get(change.page) || [];
    existing.push(change);
    byPath.set(change.page, existing);
  }
  return [...byPath.entries()].map(([path, pageChanges]) => ({ path, changes: pageChanges, kind: pageChanges.length ? "changed" : kind }));
}

export function getReportMetricNumber(content: string, key: string): number {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = content.match(new RegExp(`^- ${escaped}:\\s*(\\d+)\\s*$`, "m"));
  return match ? Number(match[1]) : 0;
}

export function extractWikiPagePaths(value: string): string[] {
  const paths = new Set<string>();
  for (const match of value.matchAll(/\b(?:sources\/)?[^\s,`]+?\.md\b/g)) {
    paths.add(match[0].replace(/[.)\]}]+$/, ""));
  }
  return [...paths];
}

export function pageName(path: string): string {
  return pathBaseName(path).replace(/\.md$/, "") || path;
}

export function isWikiPagePath(path: string): boolean {
  const normalized = path.replace(/\\/g, "/");
  return normalized.endsWith(".md") && !normalized.startsWith("sources/");
}

function isStructuredReportLine(value: string): boolean {
  return (
    /^\[\w+]\s+`[^`]+`\s+in\s+`[^`]+`:\s+/.test(value) ||
    /^`[^`]+`\s+\S+\s+\S+\s+->\s+/.test(value) ||
    /^\[(approve|reject)]\s+operation\s+\d+\s+\S+\s+risk=\w+:\s+/.test(value) ||
    /^\[\w+]\s+`[^`]+`\s+on\s+`[^`]+`\s+risk=\w+:\s+/.test(value)
  );
}
