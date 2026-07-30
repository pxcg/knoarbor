/// <reference types="vite/client" />

import type { KnoArborDesktopBridge } from "../../desktop/src/preload/types";

declare global {
  interface Window {
    knoarborDesktop?: KnoArborDesktopBridge;
  }
}

export {};
