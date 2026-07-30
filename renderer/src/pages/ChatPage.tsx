import type { KeyboardEvent } from "react";
import type { ChatAppContext } from "../appContext";
import { ExcerptIngestDialog } from "../components/ExcerptIngestDialog";
import {
  ChatCitationPreviewPanel,
  ChatContextMenu,
  ChatErrorMessage,
  ChatFollowups,
  ChatMarkdownAnswer,
  ChatStatusMessage,
  CitationList,
} from "./chat/ChatParts";
import { chatProviderStatusLabel, chatStageLabel, modelProviderOptionLabel } from "./chat/ChatModel";
import { useChatController } from "./chat/useChatController";
import { turnCanBeIngested } from "./chat/useChatSelectionIngest";

function isComposingText(event: KeyboardEvent<HTMLTextAreaElement>): boolean {
  return event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229;
}

type Props = {
  context: ChatAppContext;
};

export function ChatPage({ context }: Props) {
  const chat = useChatController(context);
  const hasConversation = chat.turns.length > 0 || chat.isSending;
  const selectionActive = chat.selectedMessageIndices.size > 0;
  const modelProvidersReady = context.modelProviders !== null;
  const needsModelSetup = modelProvidersReady && !chat.chatModelProviders.length;

  return (
    <section className="view active chat-page">
      <div className="chat-layout">
        <article className={`chat-thread-panel ${hasConversation ? "conversation-mode" : "welcome-mode"}`}>
          <div className="chat-thread">
            {!hasConversation && (
              <div className="chat-empty-state">
                <div className="chat-empty-header">
                  <h2>{context.t("chatIntroTitle")}</h2>
                  <p>{context.t("chatIntroCopy")}</p>
                </div>
              </div>
            )}

            {chat.turns.map((turn, index) => {
              const isSelected = chat.selectedMessageIndices.has(index);
              const isLatestCompletedReply = !chat.isSending
                && index === chat.turns.length - 1
                && turn.role === "assistant"
                && turn.kind !== "error"
                && turn.kind !== "status";
              return (
                <div
                  className={`chat-message ${turn.role}${isSelected ? " selected-for-ingest" : ""}`}
                  key={`${turn.role}-${index}`}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    if (chat.isSending) return;
                    chat.setContextMenu({ x: event.clientX, y: event.clientY, messageIndex: index });
                  }}
                >
                  {selectionActive && (
                    <label className="chat-select-checkbox">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => chat.toggleMessageSelection(index)}
                        disabled={chat.isSending || chat.ingestingMessages || !turnCanBeIngested(turn)}
                      />
                    </label>
                  )}
                  <div className="chat-bubble">
                    {turn.role === "assistant" && turn.answerProvenance && (
                      <span className={`chat-answer-source ${turn.answerProvenance.mode}`}>
                        {turn.answerProvenance.mode === "general_knowledge"
                          ? (context.language === "zh" ? "模型通用知识" : "Model general knowledge")
                          : turn.answerProvenance.mode.startsWith("knowledge_grounded")
                            ? (context.language === "zh" ? "知识库依据" : "Knowledge-base evidence")
                            : turn.answerProvenance.mode === "knowledge_gap"
                              ? (context.language === "zh" ? "知识库无匹配" : "No knowledge-base match")
                              : (context.language === "zh" ? "KnoArbor 功能说明" : "KnoArbor capability")}
                      </span>
                    )}
                    {turn.kind === "error" ? (
                      <ChatErrorMessage
                        message={turn.content}
                        context={context}
                        showSettings={turn.errorAction === "settings"}
                      />
                    ) : turn.kind === "status" ? (
                      <ChatStatusMessage message={turn.content} />
                    ) : turn.role === "assistant" ? (
                      <ChatMarkdownAnswer
                        content={turn.content}
                        citations={turn.citations || []}
                        context={context}
                        onOpenCitation={(citation, related) => void chat.openCitationPreview(citation, related)}
                      />
                    ) : (
                      <p>{turn.content}</p>
                    )}

                    {isLatestCompletedReply && (
                      <div className="chat-message-actions">
                        <button type="button" onClick={() => void chat.deleteTurn(index)}>
                          {context.language === "zh" ? "删除此轮" : "Delete turn"}
                        </button>
                        <button type="button" onClick={() => void chat.regenerateTurn(index)} disabled={chat.isRegenerating}>
                          {context.language === "zh" ? "重新生成" : "Regenerate"}
                        </button>
                      </div>
                    )}

                    {(!!turn.citations?.length || !!turn.hiddenEvidenceCount) && (
                      <CitationList
                        citations={turn.citations || []}
                        evidenceItems={turn.rawEvidence || []}
                        hiddenEvidenceCount={turn.hiddenEvidenceCount || 0}
                        context={context}
                        onOpenCitation={(citation, related) => void chat.openCitationPreview(citation, related)}
                      />
                    )}
                    {turn.role === "assistant" && !!turn.citations?.length && (
                      <ChatFollowups
                        citations={turn.citations}
                        context={context}
                        disabled={chat.isSending}
                        onAsk={(prompt) => void chat.submit(prompt)}
                      />
                    )}
                  </div>
                </div>
              );
            })}

            {chat.isSending && (
              <div className="chat-message assistant">
                <div className="chat-bubble">
                  <div className="chat-thinking" aria-live="polite">
                    <span />
                    <span />
                    <span />
                    <p>{chatStageLabel(chat.requestStage, context)}</p>
                  </div>
                </div>
              </div>
            )}

            {chat.selectedMessageIndices.size > 0 && (
              <div className="chat-ingest-floatbar">
                <span>{context.language === "zh"
                  ? `已选 ${chat.selectedMessageIndices.size} 条消息`
                  : `${chat.selectedMessageIndices.size} message(s) selected`}</span>
                <button className="button compact" type="button" onClick={chat.clearMessageSelection}>
                  {context.language === "zh" ? "清除" : "Clear"}
                </button>
                <button
                  className="button primary compact"
                  type="button"
                  onClick={() => void chat.ingestSelectedMessages()}
                  disabled={chat.ingestingMessages}
                >
                  {chat.ingestingMessages
                    ? (context.language === "zh" ? "摄入中..." : "Ingesting...")
                    : context.t("chatIngestExcerpt")}
                </button>
              </div>
            )}
          </div>

          <div className={`chat-composer ${hasConversation ? "in-thread" : "welcome"}`}>
            <div className="chat-input-shell">
              <textarea
                value={chat.input}
                onChange={(event) => chat.setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey && !isComposingText(event)) {
                    event.preventDefault();
                    void chat.submit();
                  }
                }}
                placeholder={context.t("chatPlaceholder")}
                rows={2}
              />
              <div className="chat-input-footer">
                <div className="chat-input-left-tools">
                  {!!context.vaultOptions.length && (
                    <div className="chat-vault-toolbar" title={context.t("activeVault")}>
                      <select
                        value={context.chatScopeVaultId}
                        onChange={(event) => context.openChatSession(null, event.target.value)}
                        disabled={chat.isSending}
                        aria-label={context.t("activeVault")}
                      >
                        {context.vaultOptions.map((vault) => (
                          <option value={vault.id} key={vault.id}>
                            {vault.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
                {!!chat.chatModelProviders.length && (
                  <div className="chat-model-toolbar" title={chatProviderStatusLabel(chat.activeChatProvider, context)}>
                    <select
                      value={chat.activeChatProvider}
                      onChange={(event) => context.setSelectedChatProvider(event.target.value)}
                      disabled={chat.isSending}
                      aria-label={context.t("model")}
                    >
                      {chat.chatModelProviders.map((provider) => (
                        <option value={provider.name} key={provider.name}>
                          {modelProviderOptionLabel(provider)}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <button
                  className={`button ${chat.isSending ? "secondary" : "primary"} chat-send-button`}
                  type="button"
                  onClick={chat.isSending ? chat.stopSending : () => void chat.submit()}
                  disabled={!chat.isSending && (!chat.input.trim() || !modelProvidersReady || needsModelSetup)}
                  title={chat.isSending ? context.t("chatStop") : context.t("chatSend")}
                >
                  {chat.isSending ? context.t("chatStop") : context.t("chatSend")}
                </button>
              </div>
            </div>
          </div>
        </article>

        {chat.contextMenu && (
          <ChatContextMenu
            contextMenu={chat.contextMenu}
            context={context}
            turns={chat.turns}
            sessionId={chat.sessionId}
            selectedMessageIndices={chat.selectedMessageIndices}
            isSending={chat.isSending}
            ingestingMessages={chat.ingestingMessages}
            ingestingExcerptKey={chat.ingestingExcerptKey}
            onToggleMessage={chat.toggleMessageSelection}
            onCompileExcerpt={chat.archiveExcerpt}
            onIngestSelected={() => void chat.ingestSelectedMessages()}
            onClose={chat.closeContextMenu}
          />
        )}

        {chat.citationPreview && (
          <ChatCitationPreviewPanel
            context={context}
            preview={chat.citationPreview}
            onClose={chat.closeCitationPreview}
          />
        )}
        <ExcerptIngestDialog
          context={context}
          draft={chat.pendingIngest}
          heading={context.t("editExcerptTitle")}
          submitting={chat.ingestingMessages}
          onChange={chat.updatePendingExcerpt}
          onCancel={chat.cancelPendingIngest}
          onConfirm={chat.confirmPendingIngest}
        />
      </div>
    </section>
  );
}
