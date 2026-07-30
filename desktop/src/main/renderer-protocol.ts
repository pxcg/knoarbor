import { net, protocol } from "electron";
import { existsSync, statSync } from "node:fs";
import { isAbsolute, join, normalize, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { desktopProduct } from "./product.js";

const RENDERER_SCHEME = "knoarbor";
const RENDERER_HOST = "renderer";

type RendererProtocolOptions = {
  assetsRoot: string;
  getServiceEndpoint: () => string | undefined;
};

export function registerRendererProtocolScheme(): void {
  protocol.registerSchemesAsPrivileged([
    {
      scheme: RENDERER_SCHEME,
      privileges: {
        secure: true,
        standard: true,
        stream: true,
        supportFetchAPI: true,
      },
    },
  ]);
}

export function registerRendererProtocol(options: RendererProtocolOptions): void {
  protocol.handle(RENDERER_SCHEME, (request) => handleRendererRequest(request, options));
}

export function rendererEntryUrl(): string {
  return `${RENDERER_SCHEME}://${RENDERER_HOST}/ui/index.html`;
}

async function handleRendererRequest(
  request: Request,
  options: RendererProtocolOptions,
): Promise<Response> {
  const url = new URL(request.url);
  if (url.host !== RENDERER_HOST) {
    return new Response(`Unknown ${desktopProduct.name} desktop host.`, { status: 404 });
  }

  const asset = resolveStaticAsset(options.assetsRoot, url.pathname);
  if (asset) {
    return net.fetch(pathToFileURL(asset).toString());
  }

  const endpoint = options.getServiceEndpoint();
  if (!endpoint) {
    return new Response(`${desktopProduct.name} local service is not available.`, { status: 503 });
  }
  const target = new URL(`${url.pathname}${url.search}`, endpoint);
  return net.fetch(new Request(target.toString(), request as RequestInit), {
    bypassCustomProtocolHandlers: true,
  });
}

function resolveStaticAsset(root: string, pathname: string): string | null {
  if (pathname === "/" || pathname === "/ui" || pathname === "/ui/") {
    return existingFile(root, "index.html");
  }
  if (!pathname.startsWith("/ui/")) {
    return null;
  }
  const relativePath = decodeURIComponent(pathname.slice("/ui/".length)) || "index.html";
  if (isUnsafeRelativePath(relativePath)) {
    return null;
  }
  const resolved = resolve(root, relativePath);
  if (!isWithinRoot(root, resolved)) {
    return null;
  }
  return existingFile(root, relativePath);
}

function existingFile(root: string, relativePath: string): string | null {
  const path = join(root, relativePath);
  if (!existsSync(path)) return null;
  return statSync(path).isFile() ? path : null;
}

function isUnsafeRelativePath(relativePath: string): boolean {
  const normalized = normalize(relativePath);
  return normalized.startsWith("..") || isAbsolute(normalized);
}

function isWithinRoot(root: string, path: string): boolean {
  const normalizedRoot = resolve(root);
  const normalizedPath = resolve(path);
  const relativePath = relative(normalizedRoot, normalizedPath);
  return relativePath === "" || (!relativePath.startsWith("..") && !isAbsolute(relativePath));
}
