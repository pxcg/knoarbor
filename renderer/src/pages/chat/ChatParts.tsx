import { useLayoutEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { type ChatCitation, type QueryRawEvidence } from "../../api/client";
import type { ChatAppContext } from "../../appContext";
import { MarkdownPreview } from "../../components/MarkdownPreview";
import { markdownRehypePlugins, markdownRemarkPlugins } from "../../components/markdownPlugins";
import { MermaidDiagram } from "./MermaidDiagram";
import {
  buildChatFollowups,
  citationExcerpt,
  citationTitle,
  groupCitations,
  relatedCitationsForRaw,
  resolveChatImageSrc,
} from "./ChatEvidence";
import { renderInlineCitations, type ChatCitationPreview, type ChatTurn } from "./ChatModel";
import { turnCanBeIngested } from "./useChatSelectionIngest";
export {
  citationSelector,
  openCitationTarget,
  readableChatError,
  resolveChatImageSrc,
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
  context: ChatAppContext;
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
  const isExcerptable = turn?.role === "assistant" && turnCanBeIngested(turn) && sessionId;
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
      {turnCanBeIngested(turn) && (
        <button type="button" onClick={() => { onToggleMessage(messageIndex); onClose(); }}>
          {isSelected ? (zh ? "取消选择此消息" : "Deselect this message") : (zh ? "选择此消息" : "Select this message")}
        </button>
      )}
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

export function ChatErrorMessage({
  message,
  context,
  showSettings,
}: {
  message: string;
  context: ChatAppContext;
  showSettings: boolean;
}) {
  return (
    <div className="chat-error-card" role="alert">
      <strong>{context.t("chatErrorTitle")}</strong>
      <p>{message}</p>
      {showSettings && (
        <div className="chat-error-actions">
          <button type="button" onClick={context.openSettings}>{context.t("openSettings")}</button>
        </div>
      )}
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
  context: ChatAppContext;
  onOpenCitation: (citation: ChatCitation, relatedCitations?: ChatCitation[]) => void;
}) {
  return (
    <div className="chat-answer-markdown">
      <ReactMarkdown
        remarkPlugins={markdownRemarkPlugins}
        rehypePlugins={markdownRehypePlugins}
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
                  onClick={() => citation && onOpenCitation(
                    citation,
                    relatedCitationsForRaw(citation, citations),
                  )}
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
  evidenceItems = [],
  hiddenEvidenceCount = 0,
  context,
  compact = false,
  onOpenCitation,
}: {
  citations: ChatCitation[];
  evidenceItems?: QueryRawEvidence[];
  hiddenEvidenceCount?: number;
  context: ChatAppContext;
  compact?: boolean;
  onOpenCitation: (citation: ChatCitation, relatedCitations?: ChatCitation[]) => void;
}) {
  const groups = groupCitations(citations, context);
  const rawCount = groups.reduce((total, group) => total + group.items.length, 0);
  const documentCountLabel = context.language === "zh"
    ? `${groups.length} 篇 · ${rawCount} 个 Raw`
    : `${groups.length} docs · ${rawCount} Raw`;
  return (
    <details className={`chat-citations ${compact ? "compact" : ""}`}>
      <summary>
        <span>{context.t("chatSourcesCompact")}</span>
        <strong>{documentCountLabel}</strong>
      </summary>
      {hiddenEvidenceCount > 0 && (
        <p className="chat-hidden-evidence">{context.t("chatHiddenEvidence").replace("{count}", String(hiddenEvidenceCount))}</p>
      )}
      <div className="chat-citation-list">
        {groups.map((group) => (
          <div className="chat-citation-group" key={group.key}>
            <button
              className="chat-citation-group-header"
              type="button"
              onClick={() => onOpenCitation(
                group.items[0].citation,
                group.items.flatMap((item) => item.relatedCitations),
              )}
            >
              <span>{group.label}</span>
              <small>
                {context.language === "zh"
                  ? `${group.items.length} 个 Raw`
                  : `${group.items.length} Raw`}
              </small>
            </button>
            {group.items.map(({ citation, index, relatedCitations }) => (
              <button
                key={`${citation.kind}-${citation.evidence_id || citation.source_unit_id || citation.path || citation.run_id}-${index}`}
                type="button"
                onClick={() => onOpenCitation(citation, relatedCitations)}
                className="chat-citation-card"
              >
                <span className="chat-citation-index">{index + 1}</span>
                <span className="chat-citation-main">
                  <strong>{citation.title || citation.source_unit_id || citation.path || citation.run_id || citation.kind}</strong>
                  <small>{citationExcerpt(citation, evidenceItems) || citation.vault_name || citation.vault_id || citation.kind}</small>
                </span>
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
  context: ChatAppContext;
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
  onClose,
}: {
  context: ChatAppContext;
  preview: ChatCitationPreview;
  onClose: () => void;
}) {
  const title = preview.page?.summary.title || citationTitle(preview.citation);
  return (
    <aside className="chat-preview-panel" aria-label={context.t("chatSourcePreview")}>
      <div className="chat-preview-header">
        <div>
          <span className="eyebrow">{context.t("chatSourcePreview")}</span>
          <h3>{title}</h3>
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
        <div className="chat-preview-state chat-preview-unavailable">
          <p>{preview.error}</p>
        </div>
      )}
      {!preview.loading && preview.page && (
        <>
          <div className="chat-preview-content">
            <MarkdownPreview
              content={preview.page.raw_content || preview.page.content}
              vaultPath={preview.citation.vault_path || context.activeVaultSelector.vault_path || context.vaultPath}
              highlightTerm={preview.highlightTerm}
              highlightTerms={preview.highlightTerms}
              scrollToHighlight
            />
          </div>
        </>
      )}
    </aside>
  );
}
