import type { RawRevisionEditorState } from "../../api/client";

type Props = {
  state: RawRevisionEditorState;
  content: string;
  error: string | null;
  language: "zh" | "en";
  pending: boolean;
  onCancel: () => void;
  onChange: (content: string) => void;
  onSave: () => void;
};

export function RawRevisionEditor({ state, content, error, language, pending, onCancel, onChange, onSave }: Props) {
  const zh = language === "zh";
  const changeRatio = approximateChangeRatio(state.content, content);
  return (
    <div className="settings-modal-backdrop" onClick={onCancel}>
      <section className="settings-modal raw-revision-editor-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <header className="settings-modal-header">
          <div>
            <h2>{zh ? "修订原始材料" : "Revise raw material"}</h2>
            <p>
              {zh
                ? "保存后将进入完整 ingest 流程，调用当前模型重新提取知识并生成新的 Raw revision。"
                : "Saving starts a full ingest with the current model to extract knowledge again and create a new Raw revision."}
            </p>
          </div>
          <button className="icon-button subtle settings-modal-close" type="button" onClick={onCancel}>✕</button>
        </header>

        <div className="raw-revision-impact warning">
          <span>{zh ? `预计改动 ${Math.round(changeRatio * 100)}%` : `Estimated change ${Math.round(changeRatio * 100)}%`}</span>
          <span>{zh ? `${state.source_unit_count} 个材料单元` : `${state.source_unit_count} source units`}</span>
          <span>{zh ? `${state.evidence_span_count} 个证据引用` : `${state.evidence_span_count} evidence references`}</span>
          <strong>{zh ? "现有投影将由本次 ingest 的新提取结果替换。" : "The new ingest result will replace the current projection."}</strong>
        </div>
        {error ? <p className="settings-action-note warning raw-revision-editor-error" role="alert">{error}</p> : null}

        <div className="settings-modal-content raw-revision-editor-content">
          <textarea value={content} onChange={(event) => onChange(event.target.value)} spellCheck={false} />
        </div>

        <div className="wiki-edit-actions">
          <button className="button secondary" type="button" onClick={onCancel}>{zh ? "取消" : "Cancel"}</button>
          <button className="button primary" type="button" disabled={pending || !content.trim() || content === state.content} onClick={onSave}>
            {pending ? (zh ? "正在提交 ingest…" : "Submitting ingest…") : (zh ? "保存并重新提取" : "Save and re-extract")}
          </button>
        </div>
      </section>
    </div>
  );
}

function approximateChangeRatio(before: string, after: string) {
  if (before === after) return 0;
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < before.length - prefix
    && suffix < after.length - prefix
    && before[before.length - suffix - 1] === after[after.length - suffix - 1]
  ) suffix += 1;
  const changed = Math.max(before.length - prefix - suffix, after.length - prefix - suffix);
  return Math.min(1, changed / Math.max(1, before.length, after.length));
}

