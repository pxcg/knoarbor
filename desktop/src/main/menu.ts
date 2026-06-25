import { app, BrowserWindow, Menu, shell, type MenuItemConstructorOptions } from "electron";
import type { DesktopCommand } from "../preload/types.js";

export function installDesktopMenu(input: { githubUrl: string }): void {
  const isMac = process.platform === "darwin";
  const template: MenuItemConstructorOptions[] = [
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: "about" },
              { type: "separator" },
              commandItem("Settings...", "CommandOrControl+,", "settings.open"),
              { type: "separator" },
              { role: "hide" },
              { role: "hideOthers" },
              { role: "unhide" },
              { type: "separator" },
              { role: "quit" },
            ],
          } satisfies MenuItemConstructorOptions,
        ]
      : []),
    {
      label: "File",
      submenu: [
        commandItem("New Chat", "CommandOrControl+N", "chat.new"),
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },
    {
      label: "Service",
      submenu: [
        commandItem("Restart Local Service", undefined, "service.restart"),
        commandItem("Open Logs", undefined, "logs.open"),
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    {
      label: "Help",
      submenu: [
        commandItem("API Docs", undefined, "docs.open"),
        {
          click: () => {
            void shell.openExternal(input.githubUrl);
          },
          label: "GitHub",
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function commandItem(
  label: string,
  accelerator: string | undefined,
  command: DesktopCommand,
): MenuItemConstructorOptions {
  return {
    accelerator,
    click: () => {
      const window = BrowserWindow.getFocusedWindow();
      window?.webContents.send("knoarbor-desktop:command", command);
    },
    label,
  };
}
