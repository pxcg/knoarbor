import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { App } from "./App";
import { getDesktopEnvironment, isDesktopApp } from "./desktop/desktopBridge";
import { productIdentity } from "./product";
import "./styles/app.css";

document.title = `${productIdentity.name} Console`;

if (isDesktopApp()) {
  document.documentElement.classList.add("desktop-shell");
  void getDesktopEnvironment().then((environment) => {
    if (!environment) return;
    document.documentElement.classList.add(`desktop-platform-${environment.platform}`);
  });
}

window.addEventListener("vite:preloadError", (event) => {
  event.preventDefault();
  const key = "knoarbor.preloadErrorReloaded";
  if (sessionStorage.getItem(key) === "true") return;
  sessionStorage.setItem(key, "true");
  window.location.reload();
});

window.addEventListener("load", () => {
  sessionStorage.removeItem("knoarbor.preloadErrorReloaded");
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
