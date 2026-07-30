import type { ReactNode } from "react";
import { Dialog } from "./Dialog";

type WorkspaceSettingsModalProps = {
  children: ReactNode;
  isOpen: boolean;
  t: (key: string) => string;
  onClose: () => void;
};

export function WorkspaceSettingsModal({ children, isOpen, t, onClose }: WorkspaceSettingsModalProps) {
  return (
    <Dialog
      closeLabel={t("close")}
      eyebrow={t("workspaceSettingsEyebrow")}
      isOpen={isOpen}
      onClose={onClose}
      title={t("workspaceSettings")}
      titleId="workspace-settings-title"
    >
      {children}
    </Dialog>
  );
}
