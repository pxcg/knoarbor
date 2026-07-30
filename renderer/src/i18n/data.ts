import type { Language, ViewName } from "../types";
import en from "./locales/en";
import zh from "./locales/zh";

type Dict = Record<string, string>;

export const viewTitles: Record<Language, Record<ViewName, string>> = {
  en: {
    chat: "Chat",
    wiki: "Knowledge Base",
    ingest: "Import",
    lint: "Lint",
    query: "Query",
    graph: "Graph",
    reports: "Run Records",
    tokens: "Token Analytics",
  },
  zh: {
    chat: "对话",
    wiki: "知识库",
    ingest: "导入资料",
    lint: "校验维护",
    query: "知识查询",
    graph: "知识图谱",
    reports: "运行记录",
    tokens: "Token 分析",
  },
};

export const navCopy: Record<Language, Record<ViewName, string>> = {
  en: {
    chat: "Ask your knowledge base",
    wiki: "Browse page content",
    ingest: "Add materials",
    lint: "Maintain knowledge",
    query: "Search knowledge",
    graph: "Explore links",
    reports: "记录与报告",
    tokens: "Analyze model cost",
  },
  zh: {
    chat: "询问知识库",
    wiki: "浏览页面内容",
    ingest: "添加资料入库",
    lint: "检查并维护",
    query: "检索知识与原文",
    graph: "查看页面关系",
    reports: "记录与报告",
    tokens: "分析模型消耗",
  },
};

export const viewSubtitles: Record<Language, Record<ViewName, string>> = {
  en: {
    chat: "Ask questions, inspect pages, read reports, and start supported KnoArbor knowledge workflows.",
    wiki: "Browse maintained pages, source Markdown, and extraction results.",
    ingest: "Choose files, folders, or saved chats and turn them into knowledge base pages.",
    lint: "Scan, diagnose, repair, and verify the current knowledge base.",
    query: "Retrieve locator pages and raw evidence for host AI tools.",
    graph: "Inspect page relations and selected nodes.",
    reports: "Review workflow history, events, and readable report details.",
    tokens: "Analyze model token usage across flows, agents, sources, and pages.",
  },
  zh: {
    chat: "询问知识库、阅读页面、理解报告，并启动受支持的 KnoArbor 知识流程。",
    wiki: "浏览已维护页面、完整 Markdown、入链和出链关系。",
    ingest: "选择文件、文件夹或已保存会话，并整理生成知识库页面。",
    lint: "扫描、诊断、修复并复验当前知识库。",
    query: "为宿主 AI 检索定位页面和原文证据。",
    graph: "查看页面关系和选中节点详情。",
    reports: "查看流程历史、运行事件和可读报告详情。",
    tokens: "按流程、Agent、来源和页面分析模型 token 消耗。",
  },
};

const dictionaries: Record<Language, Dict> = { en, zh };


export function detectLanguage(): Language {
  const saved = localStorage.getItem("knoarbor.language");
  if (saved === "zh" || saved === "en") return saved;
  return "zh";
}

export function translate(language: Language, key: string): string {
  return dictionaries[language][key] || dictionaries.en[key] || key;
}
