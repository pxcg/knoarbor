import { useState } from "react";

import type { AppContext } from "../appContext";
import { ConfigDiagnosticsPanel } from "../components/config/ConfigDiagnosticsPanel";
import {
  ConfigGeneralSection,
  SettingsDirectory,
  SettingsLoadingState,
  SettingsSectionIntro,
  type ConfigSectionId,
} from "../components/config/ConfigPageParts";
import {
  ConfigBasicSection,
  ConfigInputsSection,
  ConfigPreprocessingSection,
  ConfigRuntimeSection,
} from "../components/config/ConfigSettingsSections";
import { ConfigModelProvidersSection } from "../components/config/ConfigModelProvidersSection";
import { useConfigController } from "./config/useConfigController";

type Props = {
  context: AppContext;
  embedded?: boolean;
};

export function ConfigPage({ context, embedded = false }: Props) {
  const [activeSection, setActiveSection] = useState<ConfigSectionId>("basic");
  const controller = useConfigController(context);
  const { diagnosticsQuery, form, formQuery, saving, setForm } = controller;

  return (
    <section className={embedded ? "settings-embedded" : "view active"}>
      <article className={embedded ? "settings-embedded-panel" : "panel"}>
        {formQuery.isLoading && <SettingsLoadingState t={context.t} />}

        {form && (
          <div className="settings-workspace">
            <SettingsDirectory activeSection={activeSection} setActiveSection={setActiveSection} t={context.t} />

            <div className="settings-section-panel" role="tabpanel">
              <SettingsSectionIntro
                section={activeSection}
                t={context.t}
                saving={saving}
                canSave={Boolean(form)}
                onSave={controller.saveStructured}
                onReload={controller.reloadSettings}
                reloading={formQuery.isFetching || diagnosticsQuery.isFetching}
              />
              {activeSection === "basic" && <ConfigBasicSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "general" && <ConfigGeneralSection context={context} />}
              {activeSection === "inputs" && <ConfigInputsSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "preprocessing" && <ConfigPreprocessingSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "runtime" && <ConfigRuntimeSection form={form} setForm={setForm} t={context.t} />}
              {activeSection === "models" && (
                <ConfigModelProvidersSection
                  form={form}
                  setForm={setForm}
                  t={context.t}
                  probeResults={context.modelProbeResults}
                  pendingAction={controller.modelPendingAction}
                  onDiscover={controller.startDiscover}
                  onProbe={controller.startProbe}
                />
              )}
              {activeSection === "diagnostics" && <ConfigDiagnosticsPanel diagnostics={diagnosticsQuery.data} loading={diagnosticsQuery.isFetching} t={context.t} />}
              {activeSection === "advanced" && (
                <div className="advanced-yaml-section" id="settings-advanced">
                  <textarea className="config-editor" spellCheck={false} value={context.configContent} onChange={(event) => context.setConfigContent(event.target.value)} />
                  <button className="button primary" onClick={controller.saveYaml} disabled={saving}>
                    {saving ? context.t("running") : context.t("saveYaml")}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </article>
    </section>
  );
}
