import { useEffect } from "react";

import type { AppNotice } from "../appContext";
import { onDesktopCommand, openDesktopLogs, restartDesktopService } from "./desktopBridge";

type DesktopCommandHandlers = {
  onNewChat: () => void;
  onOpenSettings: () => void;
  refreshAll: () => Promise<boolean>;
  setNotice: (notice: AppNotice | null) => void;
  t: (key: string) => string;
};

export function useDesktopCommands({ onNewChat, onOpenSettings, refreshAll, setNotice, t }: DesktopCommandHandlers) {
  useEffect(() => {
    return onDesktopCommand((command) => {
      if (command === "settings.open") {
        onOpenSettings();
        return;
      }
      if (command === "chat.new") {
        onNewChat();
        return;
      }
      if (command === "service.restart") {
        setNotice({ message: t("serviceRestarting") });
        void restartDesktopService().then(() => refreshAll());
        return;
      }
      if (command === "logs.open") {
        void openDesktopLogs();
      }
    });
  }, [onNewChat, onOpenSettings, refreshAll, setNotice, t]);
}
