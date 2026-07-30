import type { ChatIngestTargetContext } from "../appContext";
import { Dialog } from "./Dialog";

type Props = {
  context: ChatIngestTargetContext;
  isOpen: boolean;
  title: string;
  targetVaultId: string;
  submitting?: boolean;
  onTitleChange: (value: string) => void;
  onTargetVaultChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ChatIngestTargetModal({
  context,
  isOpen,
  title,
  targetVaultId,
  submitting = false,
  onTitleChange,
  onTargetVaultChange,
  onCancel,
  onConfirm,
}: Props) {
  const vaults = context.vaultOptions.filter((vault) => !vault.virtual);
  const zh = context.language === "zh";
  return (
    <Dialog
      className="chat-ingest-target-modal"
      closeLabel={context.t("close")}
      isOpen={isOpen}
      onClose={onCancel}
      title={zh ? "入库设置" : "Import To Knowledge Base"}
    >
          <label className="field">
            <span>{zh ? "目标知识库" : "Target Knowledge Base"}</span>
            <select value={targetVaultId} onChange={(event) => onTargetVaultChange(event.target.value)} disabled={submitting || !vaults.length}>
              {vaults.map((vault) => (
                <option value={vault.id} key={vault.id}>{vault.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{zh ? "入库名称" : "Import Name"}</span>
            <input value={title} onChange={(event) => onTitleChange(event.target.value)} autoFocus />
          </label>
          <div className="settings-modal-actions">
            <button className="button secondary" type="button" onClick={onCancel} disabled={submitting}>{context.t("cancel")}</button>
            <button className="button primary" type="button" onClick={onConfirm} disabled={submitting || !vaults.length || !title.trim()}>
              {submitting ? (zh ? "入库中..." : "Importing...") : (zh ? "确认入库" : "Import")}
            </button>
          </div>
    </Dialog>
  );
}

