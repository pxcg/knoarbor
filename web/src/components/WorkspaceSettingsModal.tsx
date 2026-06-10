import { createPortal } from "react-dom";
import type { ReactNode } from "react";

type WorkspaceSettingsModalProps = {
  children: ReactNode;
  isOpen: boolean;
  t: (key: string) => string;
  onClose: () => void;
};

export function WorkspaceSettingsModal({ children, isOpen, t, onClose }: WorkspaceSettingsModalProps) {
  if (!isOpen) return null;
  return createPortal(
    <div
      className="settings-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="workspace-settings-title">
        <header className="settings-modal-header">
          <div>
            <p className="eyebrow">{t("workspaceSettingsEyebrow")}</p>
            <h2 id="workspace-settings-title">{t("workspaceSettings")}</h2>
          </div>
          <button className="icon-button subtle settings-modal-close" type="button" onClick={onClose} aria-label={t("close")}>
            ×
          </button>
        </header>
        <div className="settings-modal-content">{children}</div>
      </section>
    </div>,
    document.body,
  );
}
