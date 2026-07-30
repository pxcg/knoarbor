import type { VaultOption } from "../vaultRuntime";
import { LineIcon } from "./LineIcon";

type Props = {
  activeVaultId: string;
  label: string;
  onChange: (vaultId: string) => void;
  vaultOptions: VaultOption[];
};

export function PageVaultSwitcher({ activeVaultId, label, onChange, vaultOptions }: Props) {
  const vaults = vaultOptions.filter((vault) => !vault.virtual);
  if (vaults.length < 2) return null;
  return (
    <label className="page-vault-switcher-control" title={label}>
      <LineIcon name="wiki" />
      <select
        aria-label={label}
        className="page-vault-switcher"
        onChange={(event) => onChange(event.target.value)}
        value={activeVaultId}
      >
        {vaults.map((vault) => (
          <option key={vault.id} value={vault.id}>
            {vault.name}
          </option>
        ))}
      </select>
    </label>
  );
}

