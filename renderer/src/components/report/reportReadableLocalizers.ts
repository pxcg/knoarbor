export function localizeSeverity(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized;
  return { error: "错误", warning: "警告", info: "提示" }[normalized] || value;
}

export function localizeDecision(value: string, t: (key: string) => string) {
  if (!isChinese(t)) return value === "approve" ? "Approved" : "Rejected";
  return value === "approve" ? "通过" : "拒绝";
}

export function localizeRisk(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized;
  return { safe: "安全", low: "低", medium: "中", high: "高" }[normalized] || value;
}

export function localizeCandidateKind(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized.replace(/_/g, " ");
  return {
    deterministic_wiki_operation: "确定性维护操作",
    report_only: "仅报告",
    page_draft: "页面草稿",
  }[normalized] || normalized.replace(/_/g, " ");
}

export function localizeExecutorFit(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized.replace(/_/g, " ");
  return {
    supported_by_wiki_operation: "可由维护操作执行",
    supported_by_report_only: "适合仅报告",
    supported_by_refresh_request: "需要刷新请求",
    unsupported: "暂不支持自动执行",
  }[normalized] || normalized.replace(/_/g, " ");
}

export function localizeOperationAction(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized.replace(/_/g, " ");
  return {
    add_missing_section: "补充缺失章节",
    record_source_digest: "记录来源审计关联",
    deduplicate_section_items: "去重章节条目",
    deterministic_wiki_operation: "确定性维护操作",
    normalize_wikilink: "规范 Wiki 链接",
    remove_adjacent_duplicate_headings: "移除相邻重复标题",
    replace_wikilink: "替换 Wiki 链接",
    report_only: "仅报告",
  }[normalized] || normalized.replace(/_/g, " ");
}

export function localizeIssueCode(value: string, t: (key: string) => string) {
  const normalized = value.toLowerCase();
  if (!isChinese(t)) return normalized;
  return {
    adjacent_duplicate_heading: "相邻重复标题",
    broken_wikilink: "失效 Wiki 链接",
    duplicate_title: "重复标题",
  }[normalized] || normalized;
}

export function localizeReportSentence(value: string, t: (key: string) => string) {
  if (!isChinese(t)) return value;
  const normalized = value.trim();
  const known: Record<string, string> = {
    "No deterministic issues.": "没有确定性问题。",
    "No semantic candidates.": "没有语义候选项。",
    "No review decisions.": "没有评审决策。",
    "No queued report-only or refresh-request actions.": "没有排队的仅报告或刷新请求。",
    "No reviewed changes applied.": "没有应用评审通过的修改。",
  };
  return known[normalized] || normalized;
}

function isChinese(t: (key: string) => string): boolean {
  return t("language") === "语言";
}
