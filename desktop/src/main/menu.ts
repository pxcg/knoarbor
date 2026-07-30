import { app, BrowserWindow, Menu, shell, type MenuItemConstructorOptions } from "electron";
import type { DesktopCommand } from "../preload/types.js";

export function installDesktopMenu(input: { helpUrl: string | null }): void {
  const isMac = process.platform === "darwin";
  const platformEditItems: MenuItemConstructorOptions[] = isMac
    ? [
        { role: "pasteAndMatchStyle" },
        { role: "delete" },
        { role: "selectAll" },
        { type: "separator" },
        {
          label: "Speech",
          submenu: [{ role: "startSpeaking" }, { role: "stopSpeaking" }],
        },
      ]
    : [{ role: "delete" }, { type: "separator" }, { role: "selectAll" }];
  const editSubmenu: MenuItemConstructorOptions[] = [
    { role: "undo" },
    { role: "redo" },
    { type: "separator" },
    { role: "cut" },
    { role: "copy" },
    { role: "paste" },
    ...platformEditItems,
  ];
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
      label: "Edit",
      submenu: editSubmenu,
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
    ...(input.helpUrl
      ? [
          {
            label: "Help",
            submenu: [
              {
                click: () => {
                  void shell.openExternal(input.helpUrl as string);
                },
                label: "Help",
              },
            ],
          } satisfies MenuItemConstructorOptions,
        ]
      : []),
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
