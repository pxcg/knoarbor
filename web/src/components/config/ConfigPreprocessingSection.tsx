import { useState } from "react";

import { PathField, splitLines } from "./ConfigFormControls";
import type { SectionProps } from "./ConfigSectionTypes";

export function ConfigPreprocessingSection({ form, setForm, t }: SectionProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const returnFields = [
    ["mineru_return_md", "mineruReturnMd"],
    ["mineru_return_middle_json", "mineruReturnMiddleJson"],
    ["mineru_return_model_output", "mineruReturnModelOutput"],
    ["mineru_return_content_list", "mineruReturnContentList"],
    ["mineru_return_images", "mineruReturnImages"],
    ["mineru_response_format_zip", "mineruResponseFormatZip"],
    ["mineru_formula_enable", "mineruFormulaEnable"],
    ["mineru_table_enable", "mineruTableEnable"],
  ] as const;

  function updateMinerUBoolean(key: (typeof returnFields)[number][0], checked: boolean) {
    setForm({ ...form, [key]: checked });
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
            <button className="button secondary small-button" type="button" onClick={() => setAdvancedOpen(!advancedOpen)}>
              {advancedOpen ? t("hideAdvanced") : t("showAdvanced")}
            </button>
          </div>
          <label className="checkbox-field compact">
            <input type="checkbox" checked={form.mineru_enabled} onChange={(event) => setForm({ ...form, mineru_enabled: event.target.checked })} />
            <span>{t("nonMarkdownConnector")}</span>
          </label>
          <PathField label={t("mineruEndpoint")} value={form.mineru_endpoint} onChange={(value) => setForm({ ...form, mineru_endpoint: value })} placeholder="http://127.0.0.1:18000/file_parse" />
          {advancedOpen && (
            <div className="advanced-config-panel">
              <div className="form-grid settings-path-grid">
                <label className="field">
                  <span>{t("mineruBackend")}</span>
                  <select value={form.mineru_backend} onChange={(event) => setForm({ ...form, mineru_backend: event.target.value })}>
                    <option value="pipeline">pipeline</option>
                    <option value="vlm-engine">vlm-engine</option>
                    <option value="hybrid-engine">hybrid-engine</option>
                    <option value="vlm-http-client">vlm-http-client</option>
                    <option value="hybrid-http-client">hybrid-http-client</option>
                  </select>
                </label>
                <label className="field">
                  <span>{t("mineruParseMethod")}</span>
                  <select value={form.mineru_parse_method} onChange={(event) => setForm({ ...form, mineru_parse_method: event.target.value })}>
                    <option value="auto">auto</option>
                    <option value="txt">txt</option>
                    <option value="ocr">ocr</option>
                  </select>
                </label>
                <label className="field">
                  <span>{t("mineruTimeout")}</span>
                  <input type="number" value={form.mineru_timeout_seconds} onChange={(event) => setForm({ ...form, mineru_timeout_seconds: Number(event.target.value) })} />
                </label>
                <PathField label={t("mineruLangList")} value={form.mineru_lang_list} onChange={(value) => setForm({ ...form, mineru_lang_list: value })} />
                <PathField label={t("mineruServerUrl")} value={form.mineru_server_url} onChange={(value) => setForm({ ...form, mineru_server_url: value })} placeholder={t("optional")} />
                <label className="field">
                  <span>{t("mineruStartPage")}</span>
                  <input type="number" value={form.mineru_start_page_id} onChange={(event) => setForm({ ...form, mineru_start_page_id: Number(event.target.value) })} />
                </label>
                <label className="field">
                  <span>{t("mineruEndPage")}</span>
                  <input type="number" value={form.mineru_end_page_id} onChange={(event) => setForm({ ...form, mineru_end_page_id: Number(event.target.value) })} />
                </label>
              </div>
              <label className="field">
                <span>{t("mineruPatterns")}</span>
                <textarea className="path-list-editor compact" value={form.mineru_patterns.join("\n")} onChange={(event) => setForm({ ...form, mineru_patterns: splitLines(event.target.value) })} />
              </label>
              <div className="checkbox-grid compact-checkbox-grid">
                <label className="checkbox-field compact">
                  <input type="checkbox" checked={form.mineru_recursive} onChange={(event) => setForm({ ...form, mineru_recursive: event.target.checked })} />
                  <span>{t("mineruRecursive")}</span>
                </label>
                {returnFields.map(([key, label]) => (
                  <label className="checkbox-field compact" key={key}>
                    <input type="checkbox" checked={Boolean(form[key])} onChange={(event) => updateMinerUBoolean(key, event.target.checked)} />
                    <span>{t(label)}</span>
                  </label>
                ))}
              </div>
              <label className="field">
                <span>{t("mineruExtraFields")}</span>
                <textarea className="config-editor compact-json-editor" value={form.mineru_extra_fields_json} onChange={(event) => setForm({ ...form, mineru_extra_fields_json: event.target.value })} spellCheck={false} />
              </label>
              <p className="panel-copy compact-copy">{t("mineruAdvancedCopy")}</p>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
