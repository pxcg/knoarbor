import { useLayoutEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  type ChatCitation,
} from "../../api/client";
import type { AppContext } from "../../appContext";
import { MermaidDiagram } from "./MermaidDiagram";
import {
  buildChatFollowups,
  citationTitle,
  followupPromptForCitation,
  groupCitations,
  openCitationTarget,
  resolveChatImageSrc,
  resolveVaultAssetImageSrc,
} from "./ChatEvidence";
import { renderInlineCitations, type ChatCitationPreview, type ChatTurn } from "./ChatModel";
export {
  citationSelector,
  followupPromptForCitation,
  openCitationTarget,
  readableChatError,
  resolveChatImageSrc,
  resolveVaultAssetImageSrc,
} from "./ChatEvidence";

export function ChatStatusMessage({ message }: { message: string }) {
  return <div className="chat-status-card">{message}</div>;
}

export function ChatContextMenu({
  contextMenu,
  context,
  turns,
  sessionId,
  selectedMessageIndices,
  isSending,
  ingestingMessages,
  ingestingExcerptKey,
  onToggleMessage,
  onCompileExcerpt,
  onIngestSelected,
  onClose,
}: {
  contextMenu: { x: number; y: number; messageIndex: number };
  context: AppContext;
  turns: ChatTurn[];
  sessionId: string | null;
  selectedMessageIndices: Set<number>;
  isSending: boolean;
  ingestingMessages: boolean;
  ingestingExcerptKey: string | null;
  onToggleMessage: (index: number) => void;
  onCompileExcerpt: (turn: ChatTurn, index: number) => void;
  onIngestSelected: () => void;
  onClose: () => void;
}) {
  const { messageIndex } = contextMenu;
  const turn = turns[messageIndex];
  const isSelected = selectedMessageIndices.has(messageIndex);
  const hasTextSelection = (typeof window !== "undefined" && window.getSelection()?.toString().trim()) || false;
  const isExcerptable = turn?.role === "assistant" && turn.kind !== "error" && turn.kind !== "status" && sessionId;
  const zh = context.language === "zh";
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuPos, setMenuPos] = useState<{ left: number; top: number }>({ left: contextMenu.x, top: contextMenu.y });

  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!menu) return;
    const rect = menu.getBoundingClientRect();
    let left = contextMenu.x;
    let top = contextMenu.y;
    if (left + rect.width > window.innerWidth - 8) left = window.innerWidth - rect.width - 8;
    if (top + rect.height > window.innerHeight - 8) top = window.innerHeight - rect.height - 8;
    if (left < 4) left = 4;
    if (top < 4) top = 4;
    setMenuPos({ left, top });
  }, [contextMenu.x, contextMenu.y]);

  return (
    <div ref={menuRef} className="chat-context-menu" style={{ left: menuPos.left, top: menuPos.top }}>
      <button type="button" onClick={() => { onToggleMessage(messageIndex); onClose(); }}>
        {isSelected ? (zh ? "取消选择此消息" : "Deselect this message") : (zh ? "选择此消息" : "Select this message")}
      </button>
      {isExcerptable && hasTextSelection && (
        <button
          type="button"
          disabled={isSending || ingestingExcerptKey !== null}
          onClick={() => { onCompileExcerpt(turn, messageIndex); onClose(); }}
        >
          {ingestingExcerptKey?.startsWith(`${messageIndex}:`) ? (zh ? "导入中..." : "Importing...") : (zh ? "导入摘录" : "Import excerpt")}
        </button>
      )}
      {selectedMessageIndices.size > 0 && (
        <>
          <hr />
          <button
            type="button"
            disabled={ingestingMessages}
            onClick={() => { onIngestSelected(); }}
          >
            {ingestingMessages
              ? (zh ? "摄入中..." : "Ingesting...")
              : (zh ? `摄入选中 (${selectedMessageIndices.size})` : `Ingest selected (${selectedMessageIndices.size})`)}
          </button>
        </>
      )}
    </div>
  );
}

export function ChatErrorMessage({ message, context }: { message: string; context: AppContext }) {
  return (
    <div className="chat-error-card" role="alert">
      <strong>{context.t("chatErrorTitle")}</strong>
      <p>{message}</p>
      <div className="chat-error-actions">
        <button type="button" onClick={context.openSettings}>{context.t("openSettings")}</button>
      </div>
    </div>
  );
}

export function ChatMarkdownAnswer({
  content,
  citations,
  context,
  onOpenCitation,
}: {
  content: string;
  citations: ChatCitation[];
  context: AppContext;
  onOpenCitation: (citation: ChatCitation) => void;
}) {
  return (
    <div className="chat-answer-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => {
            const href = props.href || "";
            if (href.startsWith("#knoarbor-citation=")) {
              const citationIndex = Number(decodeURIComponent(href.slice("#knoarbor-citation=".length)));
              const citation = citations[citationIndex];
              return (
                <button
                  className="chat-inline-citation"
                  type="button"
                  disabled={!citation}
                  onClick={() => citation && onOpenCitation(citation)}
                >
                  {props.children}
                </button>
              );
            }
            return <a {...props} target="_blank" rel="noreferrer" />;
          },
          img: (props) => {
            const resolvedSrc = resolveChatImageSrc(props.src, citations, context);
            return <img {...props} src={resolvedSrc} alt={props.alt || ""} loading="lazy" />;
          },
          code: ({ className, children, ...props }) => {
            const language = /language-(\w+)/.exec(className || "")?.[1];
            const code = String(children).replace(/\n$/, "");
            if (language === "mermaid") {
              return <MermaidDiagram chart={code} />;
            }
            return <code className={className} {...props}>{children}</code>;
          },
        }}
      >
        {renderInlineCitations(content, citations.length)}
      </ReactMarkdown>
    </div>
  );
}

export function CitationList({
  citations,
  hiddenEvidenceCount = 0,
  context,
  compact = false,
  onOpenCitation,
}: {
  citations: ChatCitation[];
  hiddenEvidenceCount?: number;
  context: AppContext;
  compact?: boolean;
  onOpenCitation: (citation: ChatCitation) => void;
}) {
  const groups = groupCitations(citations, context);
  return (
    <details className={`chat-citations ${compact ? "compact" : ""}`}>
      <summary>
        <span>{context.t("chatSourcesCompact")}</span>
        <strong>{citations.length}</strong>
      </summary>
      {hiddenEvidenceCount > 0 && (
        <p className="chat-hidden-evidence">{context.t("chatHiddenEvidence").replace("{count}", String(hiddenEvidenceCount))}</p>
      )}
      <div className="chat-citation-list">
        {groups.map((group) => (
          <div className="chat-citation-group" key={group.label}>
            <span className="chat-citation-group-label">{group.label}</span>
            {group.items.map(({ citation, index }) => (
              <button
                key={`${citation.kind}-${citation.path || citation.run_id}-${index}`}
                type="button"
                onClick={() => onOpenCitation(citation)}
                className="chat-citation-card"
              >
                <span className="chat-citation-index">{index + 1}</span>
                <span className="chat-citation-main">
                  <strong>{citation.title || citation.path || citation.run_id || citation.kind}</strong>
                  <small>{citation.vault_name || citation.vault_id || citation.kind}</small>
                </span>
                {citation.path && <code>{citation.path}</code>}
              </button>
            ))}
          </div>
        ))}
      </div>
    </details>
  );
}

export function ChatFollowups({
  citations,
  context,
  disabled,
  onAsk,
}: {
  citations: ChatCitation[];
  context: AppContext;
  disabled: boolean;
  onAsk: (prompt: string) => void;
}) {
  const followups = buildChatFollowups(citations, context);
  if (!followups.length) return null;
  const questions = followups.filter((item) => item.kind === "question");
  return (
    <div className="chat-followups">
      <span className="chat-followups-title">{context.t("chatFollowups")}</span>
      {!!questions.length && (
        <div className="chat-followup-row" aria-label={context.t("chatFollowupQuestions")}>
          {questions.map((item) => (
            <button key={item.label} type="button" disabled={disabled} onClick={() => item.prompt && onAsk(item.prompt)}>
              <span>{context.t("chatAskFollowup")}</span>
              <strong>{item.label}</strong>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ChatCitationPreviewPanel({
  context,
  preview,
  onAsk,
  onClose,
}: {
  context: AppContext;
  preview: ChatCitationPreview;
  onAsk: (prompt: string) => void;
  onClose: () => void;
}) {
  const title = preview.page?.summary.title || citationTitle(preview.citation);
  const path = preview.citation.path || preview.page?.path || "";
  return (
    <aside className="chat-preview-panel" aria-label={context.t("chatSourcePreview")}>
      <div className="chat-preview-header">
        <div>
          <span className="eyebrow">{context.t("chatSourcePreview")}</span>
          <h3>{title}</h3>
          {path && <code>{path}</code>}
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label={context.t("close")}>×</button>
      </div>
      {preview.loading && (
        <div className="chat-preview-state">
          <strong>{context.t("wikiPageLoading")}</strong>
          <p>{context.t("wikiPageLoadingCopy")}</p>
        </div>
      )}
      {!preview.loading && preview.error && (
        <div className="chat-error-card">
          <strong>{context.t("chatSourcePreviewFailed")}</strong>
          <p>{preview.error}</p>
          <div className="chat-error-actions">
            <button type="button" onClick={() => openCitationTarget(preview.citation, context)}>
              {context.t("viewInKnowledgeBase")}
            </button>
          </div>
        </div>
      )}
      {!preview.loading && preview.page && (
        <>
          <div className="chat-preview-summary">
            <p>{preview.page.summary.summary || context.t("noSummary")}</p>
          </div>
          <div className="chat-preview-actions">
            <button
              className="button secondary"
              type="button"
              onClick={() => onAsk(followupPromptForCitation(preview.citation, context))}
            >
              {context.t("chatAskAboutThisPage")}
            </button>
            <button
              className="button secondary"
              type="button"
              onClick={() => openCitationTarget(preview.citation, context)}
            >
              {context.t("viewInKnowledgeBase")}
            </button>
          </div>
          <div className="chat-preview-content">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                img: (props) => {
                  const resolvedSrc = resolveVaultAssetImageSrc(props.src, preview.citation.vault_path || context.activeVaultSelector.vault_path || context.vaultPath);
                  return <img {...props} src={resolvedSrc} alt={props.alt || ""} loading="lazy" />;
                },
              }}
            >
              {preview.page.content}
            </ReactMarkdown>
          </div>
        </>
      )}
    </aside>
  );
}
