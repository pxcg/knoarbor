from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "src" / "knoarbor" / "product_manifest.json"
OUTPUTS = {
    ROOT / "renderer" / "src" / "product.ts": "renderer",
    ROOT / "desktop" / "src" / "main" / "product.ts": "desktop",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate product identity TypeScript adapters.")
    parser.add_argument("--check", action="store_true", help="Fail when generated adapters differ.")
    args = parser.parse_args()
    manifest_bytes = MANIFEST_PATH.read_bytes()
    payload = json.loads(manifest_bytes)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    expected = {
        path: render_adapter(kind, payload, digest)
        for path, kind in OUTPUTS.items()
    }
    if args.check:
        stale = [str(path.relative_to(ROOT)) for path, content in expected.items() if not path.exists() or path.read_text(encoding="utf-8") != content]
        if stale:
            print("Generated product identity adapters are stale: " + ", ".join(stale))
            return 1
        return 0
    for path, content in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return 0


def render_adapter(kind: str, payload: dict[str, Any], digest: str) -> str:
    product = payload["product"]
    environment = payload["environment"]
    desktop = payload["desktop"]
    renderer = payload["renderer"]
    links = payload["links"]
    capabilities = payload["capabilities"]
    header = f"// Generated from src/knoarbor/product_manifest.json (sha256:{digest}).\n"
    if kind == "renderer":
        return header + (
            "export const productIdentity = {\n"
            f"  defaultVaultName: {json.dumps(product['default_vault_name'])},\n"
            f"  helpUrl: {json.dumps(links['help'])},\n"
            f"  logoPath: {json.dumps(renderer['logo_path'])},\n"
            f"  name: {json.dumps(product['name'])},\n"
            f"  showHelpLink: {str(capabilities['public_help']).lower()},\n"
            "} as const;\n"
        )
    return header + (
        "export const desktopProduct = {\n"
        f"  appDataDir: {json.dumps(desktop['app_data_dir'])},\n"
        f"  appId: {json.dumps(desktop['app_id'])},\n"
        f"  appUserModelId: {json.dumps(desktop['app_user_model_id'])},\n"
        f"  defaultVaultName: {json.dumps(product['default_vault_name'])},\n"
        f"  envPrefix: {json.dumps(environment['prefix'])},\n"
        f"  helpUrl: {json.dumps(links['help'])},\n"
        f"  name: {json.dumps(product['name'])},\n"
        f"  rendererHost: {json.dumps(desktop['renderer_host'])},\n"
        f"  rendererScheme: {json.dumps(desktop['renderer_scheme'])},\n"
        f"  supportsUpdates: {str(capabilities['desktop_updates']).lower()},\n"
        "} as const;\n\n"
        "export function productEnvName(name: string): string {\n"
        "  return `${desktopProduct.envPrefix}_${name}`;\n"
        "}\n\n"
        "export function productEnv(name: string): string | undefined {\n"
        "  return process.env[productEnvName(name)]?.trim() || undefined;\n"
        "}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
