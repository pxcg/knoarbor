import type { ReactNode } from "react";
import { useState } from "react";

import { canSelectDesktopDirectory, selectDesktopDirectory } from "../../desktop/desktopBridge";

export function PresetMenu({
  ariaLabel,
  customLabel,
  label,
  onChange,
  options,
  value,
}: {
  ariaLabel: string;
  customLabel: string;
  label: string;
  onChange: (value: string) => void;
  options: string[];
  value: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="custom-select-menu provider-preset-menu">
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={ariaLabel}
        className="custom-select-trigger"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span>{label}</span>
        <span aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="custom-select-options" role="listbox">
          {options.map((option) => {
            const selected = option === value;
            const optionLabel = option || customLabel;
            return (
              <button
                aria-selected={selected}
                className={selected ? "selected" : ""}
                key={option || "custom"}
                onClick={() => {
                  onChange(option);
                  setOpen(false);
                }}
                role="option"
                type="button"
              >
                <span>{optionLabel}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ConnectorCard({ title, checked, onChange, children }: { title: string; checked: boolean; onChange: (checked: boolean) => void; children: ReactNode }) {
  return (
    <section className="settings-subcard">
      <label className="checkbox-field compact">
        <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
        <span>{title}</span>
      </label>
      {children}
    </section>
  );
}

export function PathField({
  label,
  value,
  onChange,
  className = "",
  placeholder,
  ariaLabel,
  selectDirectoryTitle,
  t,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  placeholder?: string;
  ariaLabel?: string;
  selectDirectoryTitle?: string;
  t?: (key: string) => string;
}) {
  const canSelectDirectory = Boolean(canSelectDesktopDirectory() && selectDirectoryTitle);
  const chooseDirectory = async () => {
    const result = await selectDesktopDirectory({
      defaultPath: value || placeholder,
      title: selectDirectoryTitle,
    });
    if (!result.canceled && result.path) onChange(result.path);
  };
  return (
    <label className={`field ${className}`}>
      {label && <span>{label}</span>}
      <span className="desktop-path-input">
        <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} aria-label={ariaLabel || label} />
        {canSelectDirectory && (
          <button className="button secondary path-picker-button" type="button" onClick={chooseDirectory}>
            {t ? t("chooseFolder") : "Choose"}
          </button>
        )}
      </span>
    </label>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  min = 1,
  step,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  step?: number | string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        type="number"
        min={min}
        step={step}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}
      />
    </label>
  );
}

export function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}
