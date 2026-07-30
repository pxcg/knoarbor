import type { ReactNode } from "react";

import { Dialog } from "./Dialog";

type Props = {
  cancelLabel: string;
  children: ReactNode;
  closeLabel: string;
  confirmLabel: string;
  error?: string | null;
  isOpen: boolean;
  pending?: boolean;
  pendingLabel: string;
  title: string;
  onCancel: () => void;
  onConfirm: () => void;
};

export function DeleteConfirmationDialog({
  cancelLabel,
  children,
  closeLabel,
  confirmLabel,
  error = null,
  isOpen,
  pending = false,
  pendingLabel,
  title,
  onCancel,
  onConfirm,
}: Props) {
  return (
    <Dialog
      className="delete-confirmation-dialog"
      closeLabel={closeLabel}
      isOpen={isOpen}
      onClose={() => !pending && onCancel()}
      title={title}
    >
      <div className="delete-confirmation-copy">{children}</div>
      {error ? <p className="settings-action-note warning" role="alert">{error}</p> : null}
      <div className="delete-confirmation-actions">
        <button className="button secondary" type="button" onClick={onCancel} disabled={pending}>{cancelLabel}</button>
        <button className="button danger" type="button" onClick={onConfirm} disabled={pending}>
          {pending ? pendingLabel : confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}

