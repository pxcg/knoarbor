import type { Language } from "./types";

export function userFacingError(error: unknown, language: Language, fallback?: string): string {
  const raw = error instanceof Error ? error.message : String(error || "");
  const zh = language === "zh";

  if (/abort(?:ed|error)|cancelled|canceled/i.test(raw)) return zh ? "操作已取消。" : "The operation was cancelled.";
  if (/401|403|unauthori[sz]ed|forbidden|api.?key|authentication/i.test(raw)) {
    return zh ? "模型服务认证失败，请检查 API Key 和服务配置。" : "Model service authentication failed. Check the API key and service settings.";
  }
  if (/429|rate.?limit|too many requests/i.test(raw)) {
    return zh ? "模型服务请求过于频繁，请稍后重试。" : "The model service is receiving too many requests. Try again shortly.";
  }
  if (/timeout|timed out/i.test(raw)) return zh ? "操作等待超时，请稍后重试。" : "The operation timed out. Try again shortly.";
  if (/econnrefused|failed to fetch|networkerror|service unavailable|connection refused/i.test(raw)) {
    return zh ? "暂时无法连接本地服务，请稍后重试。" : "The local service is temporarily unavailable. Try again shortly.";
  }
  if (/permission denied|eacces|eperm|not permitted/i.test(raw)) {
    return zh ? "没有访问该文件或目录的权限，请检查系统权限。" : "KnoArbor cannot access this file or folder. Check system permissions.";
  }
  if (/projection changed after the editor was opened|base_revision_id/i.test(raw)) {
    return zh ? "知识内容已更新，请关闭编辑器、刷新后再修改。" : "The knowledge changed. Close the editor, refresh, and edit again.";
  }
  if (/raw material changed after|source head changed before ingest publication/i.test(raw)) {
    return zh ? "该材料已产生更新版本，请重新打开后再修改。" : "This material has a newer revision. Open it again before editing.";
  }
  if (/materialization.*pending|knowledge view.*(?:pending|rebuild)/i.test(raw)) {
    return zh
      ? "知识库视图正在等待刷新。事实数据已保存，请重建知识库视图后重试。"
      : "The knowledge view is waiting to refresh. Facts are saved; rebuild the knowledge view and try again.";
  }
  if (/enoent|vault file not found|page not found|does not exist/i.test(raw)) {
    return zh ? "对应的本地内容不存在或已被删除。" : "The local content no longer exists or was deleted.";
  }
  if (/yaml|configuration|config.*invalid|validation/i.test(raw)) {
    return zh ? "配置内容无效，请检查相关设置。" : "The configuration is invalid. Check the related settings.";
  }
  return fallback || (zh ? "操作未能完成，请稍后重试。" : "The operation could not be completed. Try again shortly.");
}
