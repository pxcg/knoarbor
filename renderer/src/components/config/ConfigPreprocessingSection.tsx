import { PathField } from "./ConfigFormControls";
import type { ConfigForm } from "../../api/client";
import type { SectionProps } from "./ConfigSectionTypes";

type ConfigPreprocessingSectionProps = SectionProps & {
  onCommit: (nextForm: ConfigForm) => Promise<void>;
  onError: (error: unknown) => void;
};

export function ConfigPreprocessingSection({ form, setForm, t, onCommit, onError }: ConfigPreprocessingSectionProps) {
  async function commit(nextForm: ConfigForm) {
    const previousForm = form;
    setForm(nextForm);
    try {
      await onCommit(nextForm);
    } catch (error) {
      setForm((current) => current === nextForm ? previousForm : current);
      onError(error);
    }
  }

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
          <PathField
            label={t("mineruEndpoint")}
            value={form.mineru_endpoint}
            onBlur={(value) => void commit({ ...form, mineru_endpoint: value })}
            onChange={(value) => setForm({ ...form, mineru_endpoint: value })}
            placeholder="http://127.0.0.1:18000/file_parse"
          />
          <div className="advanced-config-panel">
            <div className="form-grid settings-path-grid">
              <label className="field">
                <span>{t("mineruBackend")}</span>
                <select value={form.mineru_backend} onChange={(event) => void commit({ ...form, mineru_backend: event.target.value })}>
                  <option value="pipeline">pipeline</option>
                  <option value="vlm-auto-engine">vlm-auto-engine</option>
                  <option value="hybrid-auto-engine">hybrid-auto-engine</option>
                </select>
              </label>
              <label className="field">
                <span>{t("mineruParseMethod")}</span>
                <select value={form.mineru_parse_method} onChange={(event) => void commit({ ...form, mineru_parse_method: event.target.value })}>
                  <option value="auto">auto</option>
                  <option value="txt">txt</option>
                  <option value="ocr">ocr</option>
                </select>
              </label>
              <PathField
                label={t("mineruLangList")}
                value={form.mineru_lang_list}
                onBlur={(value) => void commit({ ...form, mineru_lang_list: value })}
                onChange={(value) => setForm({ ...form, mineru_lang_list: value })}
              />
              <label className="field">
                <span>{t("mineruTimeout")}</span>
                <input
                  type="number"
                  value={form.mineru_timeout_seconds}
                  onBlur={(event) => void commit({ ...form, mineru_timeout_seconds: Number(event.target.value) })}
                  onChange={(event) => setForm({ ...form, mineru_timeout_seconds: Number(event.target.value) })}
                />
              </label>
            </div>
            <div className="checkbox-grid compact-checkbox-grid">
              <label className="checkbox-field compact">
                <input type="checkbox" checked={form.mineru_formula_enable} onChange={(event) => void commit({ ...form, mineru_formula_enable: event.target.checked })} />
                <span>{t("mineruFormulaEnable")}</span>
              </label>
              <label className="checkbox-field compact">
                <input type="checkbox" checked={form.mineru_table_enable} onChange={(event) => void commit({ ...form, mineru_table_enable: event.target.checked })} />
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
