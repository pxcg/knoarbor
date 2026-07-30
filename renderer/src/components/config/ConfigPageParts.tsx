import type { ConfigForm } from "../../api/client";
import { productIdentity } from "../../product";
import type { ConfigAppContext } from "../../appContext";
import type { AppearanceMode } from "../../types";

export type ConfigSectionId = "general" | "basic" | "inputs" | "preprocessing" | "models" | "advanced";

export type DesktopDiagnosticsView = {
  appData?: {
    configPath?: string;
    root?: string;
  };
};

export function normalizeDesktopDiagnostics(value: unknown): DesktopDiagnosticsView | null {
  if (!value || typeof value !== "object") return null;
  const appData = "appData" in value ? (value as { appData?: unknown }).appData : undefined;
  if (!appData || typeof appData !== "object") return {};
  const item = appData as { configPath?: unknown; root?: unknown };
  return {
    appData: {
      configPath: typeof item.configPath === "string" ? item.configPath : undefined,
      root: typeof item.root === "string" ? item.root : undefined,
    },
  };
}

export function modelActionKey(
  variables: unknown,
  forcedAction: "discover" | "connectivity" | "apply" | undefined,
  pending: boolean,
): string | null {
  if (!pending) return null;
  if (typeof variables === "string") return `${variables}:${forcedAction || "discover"}`;
  if (variables && typeof variables === "object" && "provider" in variables) {
    const record = variables as { provider?: unknown; level?: unknown };
    const provider = typeof record.provider === "string" ? record.provider : "";
    const action = forcedAction || (typeof record.level === "string" ? record.level : "probe");
    return provider ? `${provider}:${action}` : null;
  }
  return null;
}

const CONFIG_SECTIONS: Array<{ id: ConfigSectionId; titleKey: string; copyKey: string }> = [
  { id: "general", titleKey: "settingsSectionGeneral", copyKey: "settingsSectionGeneralCopy" },
  { id: "basic", titleKey: "settingsSectionBasic", copyKey: "settingsSectionBasicCopy" },
  { id: "inputs", titleKey: "settingsSectionInputs", copyKey: "settingsSectionInputsCopy" },
  { id: "preprocessing", titleKey: "settingsSectionPreprocessing", copyKey: "settingsSectionPreprocessingCopy" },
  { id: "models", titleKey: "settingsSectionModels", copyKey: "settingsSectionModelsCopy" },
  { id: "advanced", titleKey: "advancedYaml", copyKey: "advancedYamlCopy" },
];

const CONFIG_SECTION_GROUPS: Array<{ titleKey: string; items: ConfigSectionId[] }> = [
  { titleKey: "settingsGroupGeneral", items: ["general"] },
  { titleKey: "settingsGroupKnowledgeBase", items: ["basic", "inputs", "preprocessing"] },
  { titleKey: "settingsGroupRuntime", items: ["models"] },
  { titleKey: "settingsGroupAdvanced", items: ["advanced"] },
];

export function SettingsLoadingState({ t }: { t: (key: string) => string }) {
  return (
    <div className="settings-workspace">
      <SettingsDirectory activeSection="basic" setActiveSection={() => undefined} t={t} disabled />
      <div className="settings-section-panel">
        <div className="form-grid config-basic-grid">
          <div className="skeleton-field" />
          <div className="skeleton-field" />
        </div>
      </div>
    </div>
  );
}

const APPEARANCE_MODES: AppearanceMode[] = ["system", "light", "dark"];

export function ConfigGeneralSection({ context }: { context: ConfigAppContext }) {
  return (
    <div className="settings-card-grid single">
      <div className="settings-card">
        <div>
          <h3>{context.t("language")}</h3>
        </div>
        <div className="settings-language-options" role="group" aria-label={context.t("language")}>
          <button className={`button ${context.language === "zh" ? "primary" : "secondary"}`} type="button" onClick={() => context.setLanguage("zh")}>
            中文
          </button>
          <button className={`button ${context.language === "en" ? "primary" : "secondary"}`} type="button" onClick={() => context.setLanguage("en")}>
            EN
          </button>
        </div>
      </div>

      <div className="settings-card">
        <div>
          <h3>{context.t("appearance")}</h3>
          <p className="panel-copy">{context.t("appearanceCopy")}</p>
        </div>
        <div className="settings-language-options" role="group" aria-label={context.t("appearance")}>
          {APPEARANCE_MODES.map((mode) => (
            <button
              className={`button ${context.appearanceMode === mode ? "primary" : "secondary"}`}
              key={mode}
              type="button"
              onClick={() => context.setAppearanceMode(mode)}
            >
              {context.t(`appearance.${mode}`)}
            </button>
          ))}
        </div>
      </div>

    </div>
  );
}

export function normalizeConfigForm(form: ConfigForm): ConfigForm {
  const mineruBackendAliases: Record<string, string> = {
    "hybrid-engine": "hybrid-auto-engine",
    "vlm-engine": "vlm-auto-engine",
  };
  const requestedMineruBackend = mineruBackendAliases[form.mineru_backend || ""] || form.mineru_backend;
  const mineruBackend = ["pipeline", "vlm-auto-engine", "hybrid-auto-engine"].includes(requestedMineruBackend || "")
    ? requestedMineruBackend
    : "pipeline";

  return {
    ...form,
    vault_id: form.vault_id || "default",
    vaults:
      form.vaults?.length
        ? form.vaults
        : [
            {
              id: form.vault_id || "default",
              name: form.project_name || productIdentity.defaultVaultName,
              path: form.vault_path || "./vaults/all",
              active: true,
            },
          ],
    providers: (form.providers || []).map((provider) => ({
      ...provider,
      adapter: provider.adapter || "openai_compatible",
      tls_ca_file: provider.tls_ca_file || "",
      extra_body: provider.extra_body || {},
    })),
    enabled_connectors: form.enabled_connectors || [],
    detected_chat_source_dirs: form.detected_chat_source_dirs || {},
    markdown_enabled: false,
    markdown_roots: [],
    generic_chat_enabled: Boolean(form.generic_chat_enabled),
    generic_chat_roots: form.generic_chat_roots || [],
    generic_chat_raw_output_dir: form.generic_chat_raw_output_dir || "",
    mineru_input_dir: "",
    mineru_enabled: true,
    mineru_endpoint: form.mineru_endpoint || "http://127.0.0.1:18000/file_parse",
    mineru_parse_method: ["auto", "txt", "ocr"].includes(form.mineru_parse_method || "") ? form.mineru_parse_method : "auto",
    mineru_backend: mineruBackend || "pipeline",
    mineru_timeout_seconds: form.mineru_timeout_seconds || 600,
    mineru_patterns: form.mineru_patterns || ["*.pdf", "*.docx", "*.pptx"],
    mineru_recursive: form.mineru_recursive ?? true,
    mineru_return_md: true,
    mineru_return_middle_json: Boolean(form.mineru_return_middle_json),
    mineru_return_model_output: Boolean(form.mineru_return_model_output),
    mineru_return_content_list: Boolean(form.mineru_return_content_list),
    mineru_return_images: form.mineru_return_images ?? true,
    mineru_response_format_zip: Boolean(form.mineru_response_format_zip),
    mineru_lang_list: form.mineru_lang_list || "ch",
    mineru_formula_enable: form.mineru_formula_enable ?? true,
    mineru_table_enable: form.mineru_table_enable ?? true,
    mineru_server_url: form.mineru_server_url || "",
    mineru_start_page_id: form.mineru_start_page_id ?? 0,
    mineru_end_page_id: form.mineru_end_page_id ?? 99999,
    mineru_extra_fields_json: form.mineru_extra_fields_json || "{}",
  };
}

export function SettingsDirectory({
  activeSection,
  disabled = false,
  setActiveSection,
  t,
}: {
  activeSection: ConfigSectionId;
  disabled?: boolean;
  setActiveSection: (section: ConfigSectionId) => void;
  t: (key: string) => string;
}) {
  return (
    <aside className="settings-section-rail" role="tablist" aria-label={t("settingsSections")}>
      {CONFIG_SECTION_GROUPS.map((group) => (
        <section className="settings-section-group" key={group.titleKey}>
          <h3>{t(group.titleKey)}</h3>
          <div className="settings-section-link-list">
            {group.items.map((sectionId) => {
              const section = CONFIG_SECTIONS.find((item) => item.id === sectionId) || CONFIG_SECTIONS[0];
              return (
                <button
                  className={`settings-section-link ${activeSection === section.id ? "active" : ""}`}
                  disabled={disabled}
                  key={section.id}
                  type="button"
                  role="tab"
                  aria-selected={activeSection === section.id}
                  title={`${t(section.titleKey)} · ${t(section.copyKey)}`}
                  onClick={() => setActiveSection(section.id)}
                >
                  <strong>{t(section.titleKey)}</strong>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </aside>
  );
}
