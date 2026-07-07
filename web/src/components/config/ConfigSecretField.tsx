export function SecretField({
  label,
  onChange,
  onBlur,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  onBlur?: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <input autoComplete="off" onBlur={(event) => onBlur?.(event.target.value)} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} type="password" value={value} />
    </label>
  );
}
