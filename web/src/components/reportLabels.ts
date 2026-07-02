const reportKindKeys: Record<string, string> = {
  ingest: "reportKind.ingest",
  lint: "reportKind.lint",
  maintenance: "reportKind.maintenance",
  query: "reportKind.query",
  quality: "reportKind.quality",
};

const reportLabelKeys: Record<string, string> = {
  schema: "reportLabel.schema",
  schema_version: "reportLabel.schema",
  run_id: "reportLabel.runId",
  started_at: "reportLabel.startedAt",
  created_at: "reportLabel.createdAt",
  finished_at: "reportLabel.finishedAt",
  elapsed_seconds: "reportLabel.durationSeconds",
  duration_seconds: "reportLabel.durationSeconds",
  status: "reportLabel.status",
  mode: "reportLabel.mode",
  scope_id: "reportLabel.scopeId",
  recommended_mode: "reportLabel.recommendedMode",
  policy_triggered: "reportLabel.policyTriggered",
  deterministic_issues: "reportLabel.deterministicIssues",
  deterministic_fixes: "reportLabel.deterministicFixes",
  semantic_candidates: "reportLabel.semanticCandidates",
  review_decisions: "reportLabel.reviewDecisions",
  queued_actions: "reportLabel.queuedActions",
  operation_success_rate: "reportLabel.operationSuccessRate",
  verifications: "reportLabel.verifications",
  follow_up_required: "reportLabel.followUpRequired",
  rescan_issues: "reportLabel.rescanIssues",
  issue_delta: "reportLabel.issueDelta",
  trend_issue_delta_from_previous: "reportLabel.trendIssueDelta",
  graph_components: "reportLabel.graphComponents",
  semantic_calls: "reportLabel.semanticCalls",
  segments: "reportLabel.segments",
  total_tokens: "reportLabel.totalTokens",
  prompt_cached_tokens: "reportLabel.promptCachedTokens",
  prompt_cache_hit_tokens: "reportLabel.promptCacheHitTokens",
  prompt_cache_miss_tokens: "reportLabel.promptCacheMissTokens",
  sources: "reportLabel.sourcesProcessed",
  processed: "reportLabel.processedCount",
  skipped: "reportLabel.skippedCount",
  failed: "reportLabel.failedCount",
  provider: "reportLabel.provider",
  model: "reportLabel.model",
  vault_path: "reportLabel.vaultPath",
  config_path: "reportLabel.configPath",
  source_count: "reportLabel.sourceCount",
  sources_processed: "reportLabel.sourcesProcessed",
  processed_count: "reportLabel.processedCount",
  failed_count: "reportLabel.failedCount",
  failed_segment_count: "reportLabel.failedSegments",
  error_code: "reportLabel.errorCode",
  error_category: "reportLabel.errorCategory",
  error_retryable: "reportLabel.errorRetryable",
  error_hint: "reportLabel.errorHint",
  error_stage: "reportLabel.errorStage",
  error_type: "reportLabel.errorType",
  error_message: "reportLabel.errorMessage",
  max_segment_chars: "reportLabel.maxSegmentChars",
  created_pages: "reportLabel.createdPages",
  updated_pages: "reportLabel.updatedPages",
  written_pages: "reportLabel.writtenPages",
  touched_pages: "reportLabel.touchedPages",
  applied_operations: "reportLabel.appliedOperations",
  issue_count: "reportLabel.issueCount",
  error_count: "reportLabel.errorCount",
  warning_count: "reportLabel.warningCount",
  info_count: "reportLabel.infoCount",
  policy: "reportLabel.policy",
  base_check_issues: "reportLabel.baseCheckIssues",
  deterministic_lint: "reportLabel.deterministicLint",
  document_processing: "documentProcessing",
  scoped_lint: "reportLabel.scopedLint",
  question: "reportLabel.question",
  query: "reportLabel.query",
  max_results: "reportLabel.maxResults",
  result_count: "reportLabel.resultCount",
  context_pack_chars: "reportLabel.contextPackChars",
  trace: "reportLabel.trace",
  tokens_prompt: "reportLabel.promptTokens",
  tokens_completion: "reportLabel.completionTokens",
  tokens_total: "reportLabel.totalTokens",
  token_usage: "reportLabel.tokenUsage",
  tokens_per_second: "reportLabel.tokensPerSecond",
  latency_seconds: "reportLabel.latencySeconds",
  segment_count: "reportLabel.segments",
  source_status: "reportLabel.sourceStatus",
  segment_status: "reportLabel.segmentStatus",
  write_summary: "reportLabel.writeSummary",
  failure_summary: "reportLabel.failureSummary",
};

const directReportLabels: Record<string, { en: string; zh: string }> = {
  after_rescan: { en: "After rescan", zh: "复扫后问题" },
  approved_operations: { en: "Approved operations", zh: "已批准操作" },
  average_overall_score: { en: "Average overall score", zh: "平均总分" },
  before_rescan: { en: "Before rescan", zh: "复扫前问题" },
  candidate_count: { en: "Candidate count", zh: "候选数量" },
  component_count: { en: "Component count", zh: "连通分量数量" },
  connector: { en: "Connector", zh: "输入来源" },
  current_issue_count: { en: "Current issue count", zh: "当前问题数" },
  deterministic_lint: { en: "Deterministic lint", zh: "确定性校验" },
  document_processing_failed_count: { en: "Document processing failures", zh: "文档预处理失败" },
  failed_verifications: { en: "Failed verifications", zh: "失败验证" },
  hub_pages: { en: "Hub pages", zh: "枢纽页面" },
  isolated_page_count: { en: "Isolated page count", zh: "孤立页面数" },
  issue_delta_from_previous: { en: "Issue delta from previous", zh: "较上次问题变化" },
  largest_component_size: { en: "Largest component size", zh: "最大连通分量大小" },
  maintenance_policy: { en: "Maintenance policy", zh: "维护策略" },
  maintenance_policy_triggered: { en: "Maintenance policy triggered", zh: "维护策略是否触发" },
  node_count: { en: "Node count", zh: "节点数量" },
  previous_issue_count: { en: "Previous issue count", zh: "上次问题数" },
  previous_runs_considered: { en: "Previous runs considered", zh: "参考历史运行数" },
  persistent_issue_codes: { en: "Persistent issue codes", zh: "持续存在的问题代码" },
  quality_gate_passed: { en: "Quality gate passed", zh: "质量门禁是否通过" },
  reason: { en: "Reason", zh: "原因" },
  redacted_count: { en: "Redacted count", zh: "脱敏数量" },
  repeated_issue_codes: { en: "Repeated issue codes", zh: "重复问题代码" },
  reviewed_pages: { en: "Reviewed pages", zh: "已审查页面" },
  scoped_lint_fixes: { en: "Scoped lint fixes", zh: "局部维护修复" },
  scoped_lint_issues: { en: "Scoped lint issues", zh: "局部维护问题" },
  should_process: { en: "Should process", zh: "是否需要处理" },
  small_component_count: { en: "Small component count", zh: "小连通分量数量" },
  source_id: { en: "Source ID", zh: "资料 ID" },
  segment_status: { en: "Segment status", zh: "分段状态" },
  source_status: { en: "Source status", zh: "资料状态" },
  success_rate: { en: "Success rate", zh: "成功率" },
  warnings: { en: "Warnings", zh: "警告" },
  wrote: { en: "Wrote", zh: "是否写入" },
};

const reportSectionKeys: Record<string, string> = {
  summary: "reportSection.summary",
  inputs: "reportSection.inputs",
  outputs: "reportSection.outputs",
  operations: "reportSection.operations",
  warnings: "reportSection.warnings",
  errors: "reportSection.errors",
  verification: "reportSection.verification",
  quality: "reportSection.quality",
  issue_summary: "reportSection.issueSummary",
  trend_summary: "reportSection.trendSummary",
  graph_health: "reportSection.graphHealth",
  deterministic_issues: "reportSection.deterministicIssues",
  semantic_candidates: "reportSection.semanticCandidates",
  quality_reviews: "reportSection.qualityReviews",
  review_decisions: "reportSection.reviewDecisions",
  queued_actions: "reportSection.queuedActions",
  execution: "reportSection.execution",
  metrics: "reportSection.metrics",
  pages: "reportSection.pages",
  sources: "reportSection.sources",
  decisions: "reportSection.decisions",
  run_summary: "reportSection.summary",
  run_metadata: "reportSection.metadata",
  metadata: "reportSection.metadata",
  performance: "reportSection.performance",
  result: "reportSection.results",
  results: "reportSection.results",
  affected_pages: "reportSection.pages",
  operation_summary: "reportSection.operations",
  lint_summary: "reportSection.summary",
  query_summary: "reportSection.summary",
};

export function localizeReportKind(kind: string, t: (key: string) => string): string {
  const key = reportKindKeys[normalize(kind)];
  return key ? translateIfKnown(key, kind, t) : humanizeReportLabel(kind, t);
}

export function localizeReportLabel(label: string, t: (key: string) => string): string {
  const normalized = normalize(label);
  const reconstructed = reconstructKnownCompactKey(normalized);
  const key = reportLabelKeys[normalized] || (reconstructed ? reportLabelKeys[reconstructed] : undefined);
  if (key) return translateIfKnown(key, label, t);
  const direct = directReportLabels[normalized] || (reconstructed ? directReportLabels[reconstructed] : undefined);
  if (direct) return isChinese(t) ? direct.zh : direct.en;
  return humanizeReportLabel(label, t);
}

export function localizeReportSection(label: string, t: (key: string) => string): string {
  const key = reportSectionKeys[normalize(label)];
  return key ? translateIfKnown(key, label, t) : humanizeReportLabel(label, t);
}

export function localizeReportTitle(title: string, kind: string, t: (key: string) => string): string {
  const normalizedTitle = normalize(title);
  if (normalizedTitle.includes("ingest_report")) return t("reportTitle.ingest");
  if (normalizedTitle.includes("quality")) return t("reportTitle.quality");
  if (normalizedTitle.includes("lint_run_report")) return t("reportTitle.lintRun");
  if (normalizedTitle.includes("lint_report")) return t("reportTitle.lint");
  if (normalizedTitle.includes("query")) return t("reportTitle.query");
  return title || localizeReportKind(kind, t);
}

export function localizeReportValue(value: string, t: (key: string) => string): string {
  const trimmed = value.trim();
  const normalized = normalize(trimmed);
  const chinese = isChinese(t);
  const zhValues: Record<string, string> = {
    false: "否",
    new_source: "新资料",
    none: "无",
    not_run: "未运行",
    null: "无",
    partially_failed: "部分失败",
    processed: "已处理",
    queued: "排队中",
    running: "运行中",
    skipped: "已跳过",
    true: "是",
    unchanged: "未变化",
    waiting_external_service: "等待外部服务",
    waiting_model: "等待模型",
    written: "已写入",
  };
  const enValues: Record<string, string> = {
    false: "No",
    new_source: "New source",
    none: "None",
    not_run: "Not run",
    null: "None",
    partially_failed: "Partially completed",
    processed: "Processed",
    queued: "Queued",
    running: "Running",
    skipped: "Skipped",
    true: "Yes",
    unchanged: "Unchanged",
    waiting_external_service: "Waiting for service",
    waiting_model: "Waiting for model",
    written: "Written",
  };
  const translated = chinese ? zhValues[normalized] : enValues[normalized];
  if (translated) return translated;
  if (normalized === "n_a") return chinese ? "不适用" : "N/A";
  const issueCounts = localizeIssueCountValue(trimmed, chinese);
  if (issueCounts) return issueCounts;
  return value;
}

function translateIfKnown(key: string, fallback: string, t: (key: string) => string): string {
  const translated = t(key);
  return translated === key ? fallback : translated;
}

function humanizeReportLabel(label: string, t: (key: string) => string): string {
  const normalized = normalize(label);
  if (!normalized) return label;
  const reconstructed = reconstructKnownCompactKey(normalized);
  if (reconstructed && reconstructed !== normalized) {
    return humanizeReportLabel(reconstructed, t);
  }
  if (!isChinese(t)) {
    return normalized
      .split("_")
      .map((part) => (part.toUpperCase() === part ? part : part.charAt(0).toUpperCase() + part.slice(1)))
      .join(" ");
  }

  const zhTokens: Record<string, string> = {
    action: "动作",
    actions: "动作",
    after: "后",
    applied: "已应用",
    approved: "已批准",
    average: "平均",
    base: "基础",
    before: "前",
    call: "调用",
    calls: "调用次数",
    candidate: "候选",
    candidates: "候选",
    chars: "字符数",
    completion: "输出",
    component: "连通分量",
    components: "连通分量",
    config: "配置",
    connector: "输入来源",
    count: "数量",
    created: "创建",
    current: "当前",
    decision: "决策",
    decisions: "决策",
    delta: "变化",
    deterministic: "确定性",
    duration: "耗时",
    elapsed: "耗时",
    failed: "失败",
    fixes: "修复",
    follow: "后续",
    from: "来自",
    gate: "门禁",
    graph: "图谱",
    hub: "枢纽",
    id: "ID",
    info: "提示",
    issue: "问题",
    issues: "问题",
    largest: "最大",
    latency: "延迟",
    lint: "校验维护",
    maintenance: "维护",
    max: "最大",
    mode: "模式",
    model: "模型",
    node: "节点",
    operations: "操作",
    overall: "总分",
    page: "页面",
    pages: "页面",
    passed: "是否通过",
    per: "每",
    policy: "策略",
    previous: "上次",
    process: "处理",
    processed: "已处理",
    profile: "配置档位",
    prompt: "输入",
    quality: "质量",
    query: "查询",
    queued: "排队",
    rate: "率",
    reason: "原因",
    redacted: "脱敏",
    repeated: "重复",
    required: "是否需要",
    rescan: "复扫",
    result: "结果",
    results: "结果",
    review: "评审",
    reviewed: "已审查",
    run: "运行",
    runs: "运行",
    scope: "范围",
    scoped: "局部",
    score: "分数",
    seconds: "秒",
    semantic: "语义",
    should: "是否",
    size: "大小",
    small: "小",
    source: "资料",
    sources: "资料",
    status: "状态",
    success: "成功",
    token: "Token",
    tokens: "Tokens",
    total: "总",
    touched: "触达",
    trend: "趋势",
    triggered: "是否触发",
    updated: "更新",
    usage: "用量",
    vault: "知识库",
    verification: "验证",
    verifications: "验证",
    warning: "警告",
    warnings: "警告",
    wrote: "是否写入",
    written: "写入",
  };

  const parts = normalized.split("_").map((part) => zhTokens[part] || part);
  return parts.join("");
}

function reconstructKnownCompactKey(value: string): string | null {
  const compact = value.replace(/_/g, "");
  const known = [...Object.keys(reportLabelKeys), ...Object.keys(directReportLabels)];
  return known.find((key) => key.replace(/_/g, "") === compact) || null;
}

function isChinese(t: (key: string) => string): boolean {
  return t("language") === "语言";
}

function normalize(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[`*#[\](){}]/g, "")
    .replace(/[\s./:-]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function localizeIssueCountValue(value: string, chinese: boolean): string | null {
  if (!/^[a-z_]+=\d+(,\s*[a-z_]+=\d+)*$/.test(value)) return null;
  return value
    .split(/,\s*/)
    .map((item) => {
      const [code, count] = item.split("=");
      return `${localizeIssueCodeValue(code, chinese)}=${count}`;
    })
    .join(", ");
}

function localizeIssueCodeValue(code: string, chinese: boolean): string {
  if (!chinese) return code;
  return {
    adjacent_duplicate_heading: "相邻重复标题",
    broken_wikilink: "失效 Wiki 链接",
    duplicate_title: "重复标题",
  }[code] || code;
}
