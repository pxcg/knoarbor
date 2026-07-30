import { useCallback, useEffect, useState } from "react";

import { detectLanguage, translate } from "./i18n";
import type { AppearanceMode, Language } from "./types";

const APPEARANCE_STORAGE_KEY = "knoarbor.appearanceMode";

function isAppearanceMode(value: string | null): value is AppearanceMode {
  return value === "system" || value === "light" || value === "dark";
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function applyAppearanceMode(mode: AppearanceMode) {
  const effectiveMode = mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
  document.documentElement.classList.toggle("theme-dark", effectiveMode === "dark");
  document.documentElement.classList.toggle("theme-light", effectiveMode === "light");
  document.documentElement.style.colorScheme = effectiveMode;
}

export function getStoredAppearanceMode(): AppearanceMode {
  const stored = localStorage.getItem(APPEARANCE_STORAGE_KEY);
  return isAppearanceMode(stored) ? stored : "system";
}

export function applyStoredAppearanceMode() {
  applyAppearanceMode(getStoredAppearanceMode());
}

export function useLanguagePreference() {
  const [language, setLanguageState] = useState<Language>(() => detectLanguage());
  const setLanguage = useCallback((next: Language) => {
    localStorage.setItem("knoarbor.language", next);
    setLanguageState(next);
  }, []);
  const t = useCallback((key: string) => translate(language, key), [language]);
  return { language, setLanguage, t };
}

export function useAppearancePreference() {
  const [appearanceMode, setAppearanceModeState] = useState<AppearanceMode>(() => getStoredAppearanceMode());

  const setAppearanceMode = useCallback((next: AppearanceMode) => {
    localStorage.setItem(APPEARANCE_STORAGE_KEY, next);
    setAppearanceModeState(next);
    applyAppearanceMode(next);
  }, []);

  useEffect(() => {
    applyAppearanceMode(appearanceMode);
    if (appearanceMode !== "system") return;
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const update = () => applyAppearanceMode("system");
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [appearanceMode]);

  return { appearanceMode, setAppearanceMode };
}

export function useSidebarPreference() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem("knoarbor.sidebarCollapsed") === "true");
  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((current) => {
      const next = !current;
      localStorage.setItem("knoarbor.sidebarCollapsed", String(next));
      return next;
    });
  }, []);
  return { sidebarCollapsed, toggleSidebar };
}
