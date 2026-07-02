export function SecretField({
  configured,
  configuredLabel,
  label,
  onChange,
  placeholder,
  value,
}: {
  configured: boolean;
  configuredLabel: string;
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <label className="field">
      <span>
        {label}
        {configured && <small className="field-inline-status">{configuredLabel}</small>}
      </span>
      <input autoComplete="off" onChange={(event) => onChange(event.target.value)} placeholder={placeholder} type="password" value={value} />
    </label>
  );
}
