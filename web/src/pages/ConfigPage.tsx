import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getConfigDiagnostics, getConfigForm, saveConfig, saveConfigForm, type ConfigForm } from "../api/client";
import type { AppContext } from "../App";
import { ConfigDiagnosticsPanel } from "../components/config/ConfigDiagnosticsPanel";
import {
  ConfigBasicSection,
  ConfigInputsSection,
  ConfigModelProvidersSection,
  ConfigPreprocessingSection,
  ConfigRuntimeSection,
} from "../components/config/ConfigSettingsSections";

type Props = {
  context: AppContext;
};

export function ConfigPage({ context }: Props) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ConfigForm | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const formQuery = useQuery({
    queryKey: ["config-form", context.configPath],
    queryFn: () => getConfigForm(context.configPath),
    staleTime: 5 * 60_000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  const diagnosticsQuery = useQuery({
    queryKey: ["config-diagnostics", context.configPath],
    queryFn: () => getConfigDiagnostics(context.configPath),
    enabled: Boolean(formQuery.data),
    staleTime: 5 * 60_000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (formQuery.data) setForm(normalizeConfigForm(formQuery.data));
  }, [formQuery.data]);

  useEffect(() => {
    const error = formQuery.error || diagnosticsQuery.error;
    if (error) context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
  }, [context, diagnosticsQuery.error, formQuery.error]);

  async function updateSettingsFromDisk() {
    await queryClient.invalidateQueries({ queryKey: ["config-form"] });
    await queryClient.invalidateQueries({ queryKey: ["config-diagnostics"] });
    await formQuery.refetch();
    await diagnosticsQuery.refetch();
    await context.refreshAll();
  }

  const structuredSave = useMutation({
    mutationFn: async () => {
      if (!form) throw new Error("Configuration form is not loaded.");
      return saveConfigForm(context.configPath, form);
    },
    onSuccess: async (response) => {
      context.setConfigPath(response.config_path);
      context.setConfigExists(true);
      context.setSummary(response.summary || {});
      await updateSettingsFromDisk();
      context.setNotice({ message: `${context.t("configurationSaved")} ${response.config_path}` });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  const yamlSave = useMutation({
    mutationFn: () => saveConfig(context.configPath, context.configContent),
    onSuccess: async (response) => {
      context.setConfigPath(response.config_path);
      context.setConfigExists(true);
      context.setSummary(response.summary || {});
      await updateSettingsFromDisk();
      context.setNotice({ message: `${context.t("yamlConfigurationSaved")} ${response.config_path}` });
    },
    onError: (error) => context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true }),
  });

  const saving = structuredSave.isPending || yamlSave.isPending;

  return (
    <section className="view active">
      <div className="page-intro">
        <div>
          <p className="eyebrow">{context.t("runtimeSetup")}</p>
          <h2>{context.t("settingsTitle")}</h2>
          <p className="panel-copy">{context.t("settingsSubtitle")}</p>
        </div>
      </div>

      <article className="panel">
        <div className="panel-header">
          <div>
            <h2>{context.t("configuration")}</h2>
            <p className="panel-copy">{context.t("configurationCopy")}</p>
          </div>
          <div className="button-row">
            <button
              className="button secondary"
              onClick={async () => {
                await updateSettingsFromDisk();
                context.setNotice({ message: context.t("refreshComplete") });
              }}
              disabled={formQuery.isFetching || diagnosticsQuery.isFetching}
            >
              {context.t("refresh")}
            </button>
            <button className="button primary" onClick={() => structuredSave.mutate()} disabled={!form || saving}>
              {saving ? context.t("running") : context.t("saveSettings")}
            </button>
          </div>
        </div>

        {formQuery.isLoading && <div className="empty-state">{context.t("loading")}</div>}

        {form && (
          <>
            <ConfigBasicSection form={form} setForm={setForm} t={context.t} />
            <ConfigInputsSection form={form} setForm={setForm} t={context.t} />
            <ConfigPreprocessingSection form={form} setForm={setForm} t={context.t} />
            <ConfigRuntimeSection form={form} setForm={setForm} t={context.t} />
            <ConfigModelProvidersSection form={form} setForm={setForm} t={context.t} />
            <div className="section-divider" id="settings-diagnostics">
              <div>
                <h2>{context.t("configurationStatus")}</h2>
                <p className="panel-copy">{context.t("configurationStatusCopy")}</p>
              </div>
            </div>
            <ConfigDiagnosticsPanel diagnostics={diagnosticsQuery.data} loading={diagnosticsQuery.isFetching} t={context.t} />
          </>
        )}
      </article>

      <article className="panel" id="settings-advanced">
        <div className="panel-header">
          <div>
            <h2>{context.t("advancedYaml")}</h2>
            <p className="panel-copy">{context.t("advancedYamlCopy")}</p>
          </div>
          <button className="button secondary" onClick={() => setAdvancedOpen(!advancedOpen)}>
            {advancedOpen ? context.t("hideYaml") : context.t("showYaml")}
          </button>
        </div>
        {advancedOpen && (
          <>
            <textarea className="config-editor" spellCheck={false} value={context.configContent} onChange={(event) => context.setConfigContent(event.target.value)} />
            <button className="button primary" onClick={() => yamlSave.mutate()} disabled={saving}>
              {saving ? context.t("running") : context.t("saveYaml")}
            </button>
          </>
        )}
      </article>
    </section>
  );
}

function normalizeConfigForm(form: ConfigForm): ConfigForm {
  return {
    ...form,
    providers: form.providers || [],
    enabled_connectors: form.enabled_connectors || [],
    markdown_roots: form.markdown_roots || [],
    generic_chat_enabled: Boolean(form.generic_chat_enabled),
    generic_chat_roots: form.generic_chat_roots || [],
    generic_chat_raw_output_dir: form.generic_chat_raw_output_dir || "",
    mineru_parse_method: form.mineru_parse_method || "auto",
    mineru_backend: form.mineru_backend || "pipeline",
    mineru_timeout_seconds: form.mineru_timeout_seconds || 600,
    mineru_patterns: form.mineru_patterns || ["*.pdf", "*.docx", "*.pptx"],
    mineru_recursive: form.mineru_recursive ?? true,
    mineru_return_md: form.mineru_return_md ?? true,
    mineru_return_middle_json: Boolean(form.mineru_return_middle_json),
    mineru_return_model_output: Boolean(form.mineru_return_model_output),
    mineru_return_content_list: Boolean(form.mineru_return_content_list),
    mineru_return_images: Boolean(form.mineru_return_images),
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
