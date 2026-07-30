import { X } from "lucide-react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

type DialogProps = {
  children: ReactNode;
  className?: string;
  closeLabel: string;
  eyebrow?: string;
  footer?: ReactNode;
  isOpen: boolean;
  title: ReactNode;
  titleId?: string;
  onClose: () => void;
};

export function Dialog({ children, className, closeLabel, eyebrow, footer, isOpen, title, titleId, onClose }: DialogProps) {
  if (!isOpen) return null;
  const dialog = (
    <div
      className="settings-modal-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className={["settings-modal", className].filter(Boolean).join(" ")} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <header className="settings-modal-header">
          <div>
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            <h2 id={titleId}>{title}</h2>
          </div>
          <button className="icon-button subtle settings-modal-close" type="button" onClick={onClose} aria-label={closeLabel}>
            <X aria-hidden="true" size={18} />
          </button>
        </header>
        <div className="settings-modal-content">{children}</div>
        {footer}
      </section>
    </div>
  );
  return createPortal(dialog, document.body);
}
