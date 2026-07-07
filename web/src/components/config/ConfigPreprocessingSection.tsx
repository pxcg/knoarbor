import { PathField } from "./ConfigFormControls";
import type { SectionProps } from "./ConfigSectionTypes";

export function ConfigPreprocessingSection({ form, setForm, t }: SectionProps) {
  return (
    <>
      <div className="section-divider" id="settings-preprocessing">
        <div>
          <h2>{t("documentPreprocessing")}</h2>
          <p className="panel-copy">{t("documentPreprocessingCopy")}</p>
        </div>
      </div>
      <div className="settings-card-grid single">
        <section className="settings-subcard">
          <div className="settings-subcard-header">
            <h3>MinerU Adapter</h3>
          </div>
          <PathField label={t("mineruEndpoint")} value={form.mineru_endpoint} onChange={(value) => setForm({ ...form, mineru_endpoint: value })} placeholder="http://127.0.0.1:18000/file_parse" />
          <div className="advanced-config-panel">
            <div className="form-grid settings-path-grid">
              <label className="field">
                <span>{t("mineruBackend")}</span>
                <select value={form.mineru_backend} onChange={(event) => setForm({ ...form, mineru_backend: event.target.value })}>
                  <option value="hybrid-auto-engine">hybrid-auto-engine</option>
                  <option value="pipeline">pipeline</option>
                  <option value="vlm-auto-engine">vlm-auto-engine</option>
                </select>
              </label>
              <PathField label={t("mineruLangList")} value={form.mineru_lang_list} onChange={(value) => setForm({ ...form, mineru_lang_list: value })} />
              <label className="field">
                <span>{t("mineruTimeout")}</span>
                <input type="number" value={form.mineru_timeout_seconds} onChange={(event) => setForm({ ...form, mineru_timeout_seconds: Number(event.target.value) })} />
              </label>
            </div>
            <div className="checkbox-grid compact-checkbox-grid">
              <label className="checkbox-field compact">
                <input type="checkbox" checked={form.mineru_formula_enable} onChange={(event) => setForm({ ...form, mineru_formula_enable: event.target.checked })} />
                <span>{t("mineruFormulaEnable")}</span>
              </label>
              <label className="checkbox-field compact">
                <input type="checkbox" checked={form.mineru_table_enable} onChange={(event) => setForm({ ...form, mineru_table_enable: event.target.checked })} />
                <span>{t("mineruTableEnable")}</span>
              </label>
            </div>
            <p className="panel-copy compact-copy">{t("mineruAdvancedCopy")}</p>
          </div>
        </section>
      </div>
    </>
  );
}
