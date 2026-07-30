import type { PageDetail, PageSummary } from "../../api/client";
import type { Language } from "../../types";

export type RelatedPage = {
  page: PageSummary;
  sharedEntities: string[];
};

export type WikiSection = {
  key: string;
  title: string;
  content: string;
  index: number;
};

export type MarkdownTable = {
  headers: string[];
  rows: string[][];
};

export type ProjectionClaim = {
  id: string;
  statement: string;
  evidence: string;
};

const WIKI_SECTION_ORDER = ["summary", "claims", "relations", "synthesis", "entities", "evidence", "attachments"];

export function filterWikiPages(pages: PageSummary[]) {
  return pages.filter((page) => !isSourceRecordPage(page));
}

export function searchWikiPages(pages: PageSummary[], search: string) {
  const query = search.trim().toLowerCase();
  if (!query) return pages;
  return pages.filter((page) => {
    return `${page.title} ${page.path} ${page.summary} ${page.entities.join(" ")}`.toLowerCase().includes(query);
  });
}

export function relatedPagesByEntities(detail: PageDetail, pages: PageSummary[]): RelatedPage[] {
  const currentEntities = pageEntitySet(detail);
  if (!currentEntities.size) return [];
  return pages
    .filter((page) => page.path !== detail.path)
    .map((page) => {
      const sharedEntities = page.entities
        .map(normalizeEntity)
        .filter((entity) => entity && currentEntities.has(entity));
      return { page, sharedEntities: uniqueStrings(sharedEntities) };
    })
    .filter((item) => item.sharedEntities.length)
    .sort((left, right) => {
      if (right.sharedEntities.length !== left.sharedEntities.length) return right.sharedEntities.length - left.sharedEntities.length;
      return left.page.title.localeCompare(right.page.title);
    });
}

export function pageEntitySet(detail: PageDetail) {
  const entities = new Set<string>();
  for (const entity of detail.summary.entities || []) {
    const normalized = normalizeEntity(entity);
    if (normalized) entities.add(normalized);
  }
  for (const section of extractWikiSections(detail.content)) {
    if (!["claims", "entities", "relations"].includes(section.key)) continue;
    for (const match of section.content.matchAll(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]/g)) {
      const normalized = normalizeEntity(match[1]);
      if (normalized) entities.add(normalized);
    }
  }
  return entities;
}

export function normalizeEntity(value: string) {
  return value
    .replace(/^\[\[/, "")
    .replace(/\]\]$/, "")
    .split("|")
    .pop()
    ?.trim()
    .toLowerCase() || "";
}

export function isSourceRecordPage(page: PageSummary) {
  return page.role === "source_record" || page.directory === "sources";
}

export function extractWikiSections(content: string): WikiSection[] {
  const body = stripPageChrome(content);
  const matches = Array.from(body.matchAll(/^##\s+(.+?)\s*$/gm));
  if (!matches.length) return [];
  return matches.map((match, index) => {
    const title = match[1].trim();
    const start = (match.index || 0) + match[0].length;
    const end = matches[index + 1]?.index ?? body.length;
    return {
      key: normalizeSectionKey(title),
      title,
      content: body.slice(start, end).trim(),
      index,
    };
  }).filter((section) => section.content);
}

export function orderWikiSections(sections: WikiSection[]) {
  return [...sections].sort((left, right) => {
    const leftIndex = WIKI_SECTION_ORDER.indexOf(left.key);
    const rightIndex = WIKI_SECTION_ORDER.indexOf(right.key);
    if (leftIndex === -1 && rightIndex === -1) return left.index - right.index;
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  });
}

export function parseMarkdownTable(content: string): MarkdownTable | null {
  const lines = content.split("\n").map((line) => line.trim()).filter(Boolean);
  const headerIndex = lines.findIndex((line, index) => line.startsWith("|") && lines[index + 1]?.startsWith("|") && /^\|?\s*:?-{3,}/.test(lines[index + 1]));
  if (headerIndex < 0) return null;
  const headers = splitMarkdownTableRow(lines[headerIndex]);
  const rows = lines.slice(headerIndex + 2).filter((line) => line.startsWith("|")).map(splitMarkdownTableRow);
  return headers.length && rows.length ? { headers, rows } : null;
}

export function parseProjectionClaims(content: string): ProjectionClaim[] {
  const matches = Array.from(content.matchAll(/^###\s+([^\n]+)\s*$/gm));
  return matches.map((match, index) => {
    const start = (match.index || 0) + match[0].length;
    const end = matches[index + 1]?.index ?? content.length;
    const body = content.slice(start, end).trim();
    const evidenceStart = body.search(/^(?:>|Source:)/m);
    return {
      id: match[1].trim(),
      statement: (evidenceStart < 0 ? body : body.slice(0, evidenceStart)).trim(),
      evidence: evidenceStart < 0 ? "" : body.slice(evidenceStart).trim(),
    };
  }).filter((claim) => claim.statement);
}

export function plainCellText(value: string) {
  return value
    .replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g, (_match, target: string, alias: string | undefined) => alias || target)
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/^#+\s*/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function wikiSectionLabel(key: string, title: string, language: Language) {
  if (language !== "zh") return title;
  const labels: Record<string, string> = {
    summary: "摘要",
    claims: "核心断言",
    relations: "关系三元组",
    synthesis: "综合说明",
    entities: "实体",
    evidence: "证据",
    attachments: "附件",
  };
  return labels[key] || title;
}

function splitMarkdownTableRow(line: string) {
  return line.replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, "|").trim());
}

function stripPageChrome(content: string) {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/^# .+?\n+---\s*\n[\s\S]*?\n---\s*\n?/, "")
    .replace(/^---\s*\n[\s\S]*?\n---\s*\n?/, "")
    .replace(/^# .+?\n+/, "")
    .trim();
}

function normalizeSectionKey(title: string) {
  return title.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function uniqueStrings(values: string[]) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (!value || seen.has(value)) continue;
    seen.add(value);
    result.push(value);
  }
  return result;
}
