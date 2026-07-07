import { useCallback, useState } from "react";

import { detectLanguage, translate } from "./i18n";
import type { Language } from "./types";

export function useLanguagePreference() {
  const [language, setLanguageState] = useState<Language>(() => detectLanguage());
  const setLanguage = useCallback((next: Language) => {
    localStorage.setItem("knoarbor.language", next);
    setLanguageState(next);
  }, []);
  const t = useCallback((key: string) => translate(language, key), [language]);
  return { language, setLanguage, t };
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
