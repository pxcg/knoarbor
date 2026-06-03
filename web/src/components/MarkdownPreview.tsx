import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export type MarkdownPreviewProps = {
  content: string;
  className?: string;
  stripFrontmatter?: boolean;
  currentDocPath?: string;
  onOpenDocLink?: (path: string) => void;
  onOpenWikiPage?: (path: string) => void;
};

export function MarkdownPreview({
  content,
  className,
  stripFrontmatter = false,
  currentDocPath,
  onOpenDocLink,
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
              currentDocPath={currentDocPath}
              onOpenDocLink={onOpenDocLink}
              onOpenWikiPage={onOpenWikiPage}
            />
          ),
        }}
      >
        {renderedContent}
      </ReactMarkdown>
    </div>
  );
}

function MarkdownLink(
  props: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
    currentDocPath?: string;
    onOpenDocLink?: (path: string) => void;
    onOpenWikiPage?: (path: string) => void;
  },
) {
  const { currentDocPath, onOpenDocLink, onOpenWikiPage, href, children, ...rest } = props;
  if (href?.startsWith("#knoarbor-wiki=")) {
    const pagePath = decodeURIComponent(href.slice("#knoarbor-wiki=".length));
    return (
      <button className="wiki-inline-link" type="button" onClick={() => onOpenWikiPage?.(pagePath)}>
        {children}
      </button>
    );
  }
  const docPath = resolveDocPath(href, currentDocPath);
  if (docPath && onOpenDocLink) {
    return (
      <button className="wiki-inline-link" type="button" onClick={() => onOpenDocLink(docPath)}>
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
  if (/^(sources|entities|concepts|comparisons|queries|workflows)\//.test(clean)) {
    return clean.endsWith(".md") ? clean : `${clean}.md`;
  }
  return clean.endsWith(".md") ? clean : `${clean}.md`;
}

function resolveDocPath(href: string | undefined, currentDocPath: string | undefined) {
  if (!href || href.startsWith("#") || /^[a-z][a-z0-9+.-]*:/i.test(href)) return null;
  const [pathPart] = href.split("#");
  if (!pathPart) return null;
  const normalized = normalizeRelativePath(pathPart, currentDocPath);
  if (!normalized || !normalized.endsWith(".md")) return null;
  return normalized;
}

function normalizeRelativePath(pathPart: string, currentDocPath: string | undefined) {
  const raw = pathPart.replace(/\\/g, "/").replace(/^\/+/, "");
  const withoutDocsPrefix = raw.startsWith("docs/") ? raw.slice("docs/".length) : raw;
  const withoutLocalePrefix = withoutDocsPrefix.startsWith("zh/") ? withoutDocsPrefix.slice("zh/".length) : withoutDocsPrefix;
  if (!withoutLocalePrefix.startsWith(".")) return collapsePath(withoutLocalePrefix);
  const baseParts = currentDocPath?.includes("/") ? currentDocPath.split("/").slice(0, -1) : [];
  return collapsePath([...baseParts, ...withoutLocalePrefix.split("/")].join("/"));
}

function collapsePath(path: string) {
  const parts: string[] = [];
  for (const part of path.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (!parts.length) return null;
      parts.pop();
    }
    else parts.push(part);
  }
  return parts.join("/");
}
