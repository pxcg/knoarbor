import { useEffect } from "react";

import { onDesktopCommand, openDesktopLogs, restartDesktopService } from "./desktopBridge";

type DesktopCommandHandlers = {
  onNewChat: () => void;
  onOpenSettings: () => void;
  refreshAll: () => Promise<boolean>;
};

export function useDesktopCommands({ onNewChat, onOpenSettings, refreshAll }: DesktopCommandHandlers) {
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
        void restartDesktopService().then(() => refreshAll());
        return;
      }
      if (command === "logs.open") {
        void openDesktopLogs();
      }
    });
  }, [onNewChat, onOpenSettings, refreshAll]);
}
