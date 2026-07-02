import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export type MarkdownPreviewProps = {
  content: string;
  className?: string;
  stripFrontmatter?: boolean;
  vaultPath?: string;
  onOpenWikiPage?: (path: string) => void;
};

export function MarkdownPreview({
  content,
  className,
  stripFrontmatter = false,
  vaultPath,
  onOpenWikiPage,
}: MarkdownPreviewProps) {
  const withoutFrontmatter = stripFrontmatter ? removeYamlFrontmatter(content) : content;
  const renderedContent = renderWikiLinks(withoutFrontmatter);
  return (
    <div className={`markdown-rendered ${className || ""}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => (
            <MarkdownLink
              {...props}
              onOpenWikiPage={onOpenWikiPage}
            />
          ),
          img: (props) => (
            <MarkdownImage {...props} vaultPath={vaultPath} />
          ),
        }}
      >
        {renderedContent}
      </ReactMarkdown>
    </div>
  );
}

function MarkdownImage(
  props: React.ImgHTMLAttributes<HTMLImageElement> & {
    vaultPath?: string;
  },
) {
  const { vaultPath, src, alt, ...rest } = props;
  const resolvedSrc = resolveImageSrc(src, vaultPath);
  return <img src={resolvedSrc} alt={alt || ""} {...rest} loading="lazy" />;
}

function resolveImageSrc(src: string | undefined, vaultPath?: string): string | undefined {
  if (!src) return src;
  const existingVaultAssetPath = vaultAssetPathFromApiSrc(src);
  if (existingVaultAssetPath && vaultPath) {
    return `/ui/api/vault-assets/${encodeURIComponent(existingVaultAssetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
  }
  if (/^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("//") || src.startsWith("/")) {
    return src;
  }
  const assetPath = vaultAssetPathFromSrc(src);
  if (assetPath && vaultPath) {
    return `/ui/api/vault-assets/${encodeURIComponent(assetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
  }
  return src;
}

function vaultAssetPathFromSrc(src: string): string | null {
  let cleaned = src.replace(/\\/g, "/").replace(/^\.\//, "");
  if (cleaned.startsWith("../assets/")) cleaned = cleaned.slice("../assets/".length);
  else if (cleaned.startsWith("raw/assets/")) cleaned = cleaned.slice("raw/assets/".length);
  else if (cleaned.startsWith("assets/")) cleaned = cleaned.slice("assets/".length);
  if (/^(images|media|pages|tables)\//.test(cleaned)) return cleaned;
  return null;
}

function vaultAssetPathFromApiSrc(src: string): string | null {
  let pathname = src;
  try {
    pathname = new URL(src, "http://knoarbor.local").pathname;
  } catch {
    pathname = src.split("?", 1)[0];
  }
  const prefix = "/ui/api/vault-assets/";
  if (!pathname.startsWith(prefix)) return null;
  const encoded = pathname.slice(prefix.length);
  if (!encoded) return null;
  try {
    return decodeURIComponent(encoded);
  } catch {
    return encoded;
  }
}

function MarkdownLink(
  props: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
    onOpenWikiPage?: (path: string) => void;
  },
) {
  const { onOpenWikiPage, href, children, ...rest } = props;
  if (href?.startsWith("#knoarbor-wiki=")) {
    const pagePath = decodeURIComponent(href.slice("#knoarbor-wiki=".length));
    return (
      <button className="wiki-inline-link" type="button" onClick={() => onOpenWikiPage?.(pagePath)}>
        {children}
      </button>
    );
  }
  return <a {...rest} href={href} target="_blank" rel="noreferrer">{children}</a>;
}

function removeYamlFrontmatter(content: string) {
  return content.replace(/^(\s*# .+?\n+)?---\s*\n[\s\S]*?\n---\s*\n?/, (_match, heading: string | undefined) => heading || "").trimStart();
}

function renderWikiLinks(content: string) {
  return content.replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g, (_match, rawTarget: string, rawAlias: string | undefined) => {
    const target = normalizeWikiPath(rawTarget);
    const label = (rawAlias || rawTarget).trim();
    return `[${label}](#knoarbor-wiki=${encodeURIComponent(target)})`;
  });
}

function normalizeWikiPath(target: string) {
  const clean = target.trim();
  if (/^sources\//.test(clean)) {
    return clean.endsWith(".md") ? clean : `${clean}.md`;
  }
  return clean.endsWith(".md") ? clean : `${clean}.md`;
}
