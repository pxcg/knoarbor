import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export type MarkdownPreviewProps = {
  content: string;
  className?: string;
  stripFrontmatter?: boolean;
  vaultPath?: string;
  onOpenWikiPage?: (path: string) => void;
  highlightTerm?: string | null;
  onHighlightTerm?: (term: string) => void;
};

export function MarkdownPreview({
  content,
  className,
  stripFrontmatter = false,
  vaultPath,
  onOpenWikiPage,
  highlightTerm,
  onHighlightTerm,
}: MarkdownPreviewProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const withoutFrontmatter = stripFrontmatter ? removeYamlFrontmatter(content) : content;
  const renderedContent = renderWikiLinks(withoutFrontmatter);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    unwrapEntityHighlights(root);
    const term = highlightTerm?.trim();
    if (!term || term.length < 2) return;
    highlightRenderedTerm(root, term);
  }, [renderedContent, highlightTerm]);

  return (
    <div className={`markdown-rendered ${className || ""}`.trim()} ref={rootRef}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => (
            <MarkdownLink
              {...props}
              onOpenWikiPage={onOpenWikiPage}
              onHighlightTerm={onHighlightTerm}
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
    return `/vault-assets/${encodeURIComponent(existingVaultAssetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
  }
  if (/^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("//") || src.startsWith("/")) {
    return src;
  }
  const assetPath = vaultAssetPathFromSrc(src);
  if (assetPath && vaultPath) {
    return `/vault-assets/${encodeURIComponent(assetPath)}?vault_path=${encodeURIComponent(vaultPath)}`;
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
  const prefix = "/vault-assets/";
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
    onHighlightTerm?: (term: string) => void;
  },
) {
  const { onOpenWikiPage, onHighlightTerm, href, children, ...rest } = props;
  if (href?.startsWith("#knoarbor-wiki=")) {
    const pagePath = decodeURIComponent(href.slice("#knoarbor-wiki=".length));
    const label = childrenToText(children) || pagePath.replace(/\.md$/, "");
    return (
      <button
        className="wiki-inline-link"
        type="button"
        onClick={() => {
          onHighlightTerm?.(label);
          onOpenWikiPage?.(pagePath);
        }}
      >
        {children}
      </button>
    );
  }
  return <a {...rest} href={href} target="_blank" rel="noreferrer">{children}</a>;
}

function childrenToText(children: React.ReactNode): string {
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(childrenToText).join("");
  return "";
}

function highlightRenderedTerm(root: HTMLElement, term: string) {
  const escaped = escapeRegExp(term);
  const pattern = new RegExp(escaped, "gi");
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || !node.nodeValue?.trim()) return NodeFilter.FILTER_REJECT;
      if (parent.closest("code, pre, script, style, textarea, input")) return NodeFilter.FILTER_REJECT;
      pattern.lastIndex = 0;
      return pattern.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (const node of nodes) {
    const text = node.nodeValue || "";
    pattern.lastIndex = 0;
    const fragment = document.createDocumentFragment();
    let lastIndex = 0;
    for (const match of text.matchAll(pattern)) {
      const index = match.index ?? 0;
      if (index > lastIndex) fragment.append(document.createTextNode(text.slice(lastIndex, index)));
      const mark = document.createElement("mark");
      mark.className = "wiki-entity-highlight";
      mark.textContent = match[0];
      fragment.append(mark);
      lastIndex = index + match[0].length;
    }
    if (lastIndex < text.length) fragment.append(document.createTextNode(text.slice(lastIndex)));
    node.parentNode?.replaceChild(fragment, node);
  }
}

function unwrapEntityHighlights(root: HTMLElement) {
  for (const mark of Array.from(root.querySelectorAll("mark.wiki-entity-highlight"))) {
    mark.replaceWith(document.createTextNode(mark.textContent || ""));
  }
  root.normalize();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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
