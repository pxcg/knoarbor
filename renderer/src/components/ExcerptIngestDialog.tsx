import type { ExcerptIngestAppContext } from "../appContext";
import { excerptDraftIsValid, type ExcerptIngestDraft } from "../ingest/excerptIngest";
import { Dialog } from "./Dialog";

type Props = {
  context: ExcerptIngestAppContext;
  draft: ExcerptIngestDraft | null;
  heading?: string;
  error?: string | null;
  submitting?: boolean;
  onChange: (draft: ExcerptIngestDraft) => void;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ExcerptIngestDialog({ context, draft, heading, error, submitting = false, onChange, onCancel, onConfirm }: Props) {
  const vaults = context.vaultOptions.filter((vault) => !vault.virtual);
  if (!draft) return null;

  return (
    <Dialog
      className="excerpt-ingest-dialog"
      closeLabel={context.t("close")}
      isOpen
      onClose={onCancel}
      title={heading || context.t("customInputTitle")}
    >
      <div className="excerpt-ingest-form">
        <div className="excerpt-ingest-meta">
          <label className="field">
            <span>{context.t("customInputName")}</span>
            <input
              value={draft.title}
              onChange={(event) => onChange({ ...draft, title: event.target.value })}
              disabled={submitting}
              autoFocus
            />
          </label>
          <label className="field">
            <span>{context.t("customInputVault")}</span>
            <select
              value={draft.targetVaultId}
              onChange={(event) => onChange({ ...draft, targetVaultId: event.target.value })}
              disabled={submitting || !vaults.length}
            >
              {vaults.map((vault) => <option value={vault.id} key={vault.id}>{vault.name}</option>)}
            </select>
          </label>
        </div>
        <label className="field excerpt-ingest-content">
          <span>{context.t("customInputContent")}</span>
          <textarea
            value={draft.content}
            onChange={(event) => onChange({ ...draft, content: event.target.value })}
            placeholder={context.t("customInputPlaceholder")}
            disabled={submitting}
          />
        </label>
        {error && <p className="settings-action-note warning" role="alert">{error}</p>}
        <div className="settings-modal-actions">
          <button className="button secondary" type="button" onClick={onCancel} disabled={submitting}>
            {context.t("cancel")}
          </button>
          <button className="button primary" type="button" onClick={onConfirm} disabled={submitting || !excerptDraftIsValid(draft)}>
            {submitting ? context.t("customInputSubmitting") : context.t("runIngest")}
          </button>
        </div>
      </div>
    </Dialog>
  );
}
