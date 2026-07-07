import { useState } from "react";

import type { AppContext } from "../appContext";
import {
  ConfigGeneralSection,
  SettingsDirectory,
  SettingsLoadingState,
  type ConfigSectionId,
} from "../components/config/ConfigPageParts";
import {
  ConfigBasicSection,
  ConfigInputsSection,
  ConfigPreprocessingSection,
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
  const { form, formQuery, saving, setForm } = controller;

  return (
    <section className={embedded ? "settings-embedded" : "view active"}>
      <article className={embedded ? "settings-embedded-panel" : "panel"}>
        {formQuery.isLoading && <SettingsLoadingState t={context.t} />}

        {form && (
          <div className="settings-workspace">
            <SettingsDirectory activeSection={activeSection} setActiveSection={setActiveSection} t={context.t} />

            <div className="settings-section-panel" role="tabpanel">
              {activeSection === "basic" && <ConfigBasicSection form={form} setForm={setForm} t={context.t} onCommit={controller.commitFormSnapshot} onError={context.setNotice} />}
              {activeSection === "general" && <ConfigGeneralSection context={context} form={form} setForm={setForm} onCommit={controller.commitFormSnapshot} onError={context.setNotice} />}
              {activeSection === "inputs" && <ConfigInputsSection form={form} setForm={setForm} t={context.t} onCommit={controller.commitFormSnapshot} onError={context.setNotice} />}
              {activeSection === "preprocessing" && <ConfigPreprocessingSection form={form} setForm={setForm} t={context.t} onCommit={controller.commitFormSnapshot} onError={context.setNotice} />}
              {activeSection === "models" && (
                <ConfigModelProvidersSection
                  form={form}
                  setForm={setForm}
                  t={context.t}
                  probeResults={context.modelProbeResults}
                  pendingAction={controller.modelPendingAction}
                  onDiscover={controller.startDiscover}
                  onCommit={controller.commitFormSnapshot}
                  onError={context.setNotice}
                />
              )}
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
