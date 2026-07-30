import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";

import { resolveVaultAssetImageSrc } from "../vaultAssetPaths";
import { markdownRehypePlugins, markdownRemarkPlugins } from "./markdownPlugins";

const EMPTY_HIGHLIGHT_TERMS: string[] = [];

export type MarkdownPreviewProps = {
  content: string;
  className?: string;
  stripFrontmatter?: boolean;
  vaultPath?: string;
  onOpenWikiPage?: (path: string) => void;
  highlightTerm?: string | null;
  highlightTerms?: string[];
  onHighlightTerm?: (term: string) => void;
  scrollToHighlight?: boolean;
};

export function MarkdownPreview({
  content,
  className,
  stripFrontmatter = false,
  vaultPath,
  onOpenWikiPage,
  highlightTerm,
  highlightTerms = EMPTY_HIGHLIGHT_TERMS,
  onHighlightTerm,
  scrollToHighlight = false,
}: MarkdownPreviewProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const withoutFrontmatter = stripFrontmatter ? removeYamlFrontmatter(content) : content;
  const renderedContent = renderWikiLinks(withoutFrontmatter);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    unwrapEntityHighlights(root);
    const terms = uniqueHighlightTerms(highlightTerm, highlightTerms);
    if (!terms.length) return;
    const matches = highlightRenderedTerms(root, terms);
    const firstMatch = terms.map((term) => matches.get(term)).find(Boolean) || null;
    const focusedMatch = highlightTerm ? matches.get(highlightTerm.trim()) || null : null;
    const scrollTarget = focusedMatch || firstMatch;
    if (!scrollToHighlight || !scrollTarget) return;
    const scrollContainer = root.parentElement;
    let nestedFrame = 0;
    const frame = window.requestAnimationFrame(() => {
      nestedFrame = window.requestAnimationFrame(() => {
        if (!scrollContainer?.isConnected || !scrollTarget.isConnected) return;
        const containerRect = scrollContainer.getBoundingClientRect();
        const targetRect = scrollTarget.getBoundingClientRect();
        const centeredOffset = targetRect.top
          - containerRect.top
          - Math.max(0, (scrollContainer.clientHeight - targetRect.height) / 2);
        scrollContainer.scrollTo({
          top: Math.max(0, scrollContainer.scrollTop + centeredOffset),
          behavior: "auto",
        });
      });
    });
    return () => {
      window.cancelAnimationFrame(frame);
      if (nestedFrame) window.cancelAnimationFrame(nestedFrame);
    };
  }, [renderedContent, highlightTerm, highlightTerms, scrollToHighlight]);

  return (
    <div className={`markdown-rendered ${className || ""}`.trim()} ref={rootRef}>
      <ReactMarkdown
        remarkPlugins={markdownRemarkPlugins}
        rehypePlugins={markdownRehypePlugins}
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

function uniqueHighlightTerms(focused: string | null | undefined, related: string[]) {
  const seen = new Set<string>();
  const output: string[] = [];
  for (const value of [focused, ...related]) {
    const term = value?.trim();
    if (!term || term.length < 2 || seen.has(term)) continue;
    seen.add(term);
    output.push(term);
  }
  return output;
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
  return resolveVaultAssetImageSrc(src, vaultPath);
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

type RenderedCharacter = {
  node: Text;
  startOffset: number;
  endOffset: number;
};

type RenderedTextIndex = {
  text: string;
  characters: RenderedCharacter[];
};

type HighlightRange = {
  key: number;
  start: number;
  end: number;
};

type NodeHighlightRange = {
  key: number;
  startOffset: number;
  endOffset: number;
};

function highlightRenderedTerms(root: HTMLElement, terms: string[]) {
  const matches = new Map<string, HTMLElement>();
  const remaining: string[] = [];
  for (const term of terms) {
    const section = markdownSection(term);
    if (section) {
      const heading = Array.from(root.querySelectorAll<HTMLElement>(`h${section.level}`))
        .find((element) => normalizeText(element.innerText) === normalizeText(section.title));
      if (heading) {
        const match = highlightSection(heading, section.level);
        if (match) matches.set(term, match);
        continue;
      }
    }
    remaining.push(term);
  }

  const rendered = buildRenderedTextIndex(root);
  const ranges = collectHighlightRanges(rendered.text, remaining);
  applyHighlightRanges(rendered, ranges);
  for (const [key, term] of remaining.entries()) {
    const exact = root.querySelector<HTMLElement>(`mark.wiki-entity-highlight[data-highlight-key="${key}"]`);
    if (exact) {
      matches.set(term, exact);
      continue;
    }
    const fallback = highlightRenderedTermFallback(root, term);
    if (fallback) matches.set(term, fallback);
  }
  return matches;
}

function buildRenderedTextIndex(root: HTMLElement): RenderedTextIndex {
  const characters: RenderedCharacter[] = [];
  let text = "";
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || !node.nodeValue) return NodeFilter.FILTER_REJECT;
      if (parent.closest("code, pre, script, style, textarea, input")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    const value = node.nodeValue || "";
    for (let offset = 0; offset < value.length;) {
      const codePoint = value.codePointAt(offset);
      if (codePoint === undefined) break;
      const character = String.fromCodePoint(codePoint);
      const endOffset = offset + character.length;
      const normalized = canonicalCharacters(character);
      for (const normalizedCharacter of normalized) {
        text += normalizedCharacter;
        characters.push({ node, startOffset: offset, endOffset });
      }
      offset = endOffset;
    }
  }
  return { text, characters };
}

function collectHighlightRanges(renderedText: string, terms: string[]) {
  const ranges: HighlightRange[] = [];
  for (const [key, term] of terms.entries()) {
    const normalizedTerm = canonicalCharacters(markdownVisibleText(term));
    if (normalizedTerm.length < 2) continue;
    let offset = 0;
    while (offset <= renderedText.length - normalizedTerm.length) {
      const start = renderedText.indexOf(normalizedTerm, offset);
      if (start < 0) break;
      const end = start + normalizedTerm.length;
      if (!ranges.some((range) => start < range.end && end > range.start)) {
        ranges.push({ key, start, end });
      }
      offset = end;
    }
  }
  return ranges;
}

function applyHighlightRanges(rendered: RenderedTextIndex, ranges: HighlightRange[]) {
  const byNode = new Map<Text, NodeHighlightRange[]>();
  for (const range of ranges) {
    let currentNode: Text | null = null;
    let currentRange: NodeHighlightRange | null = null;
    for (let index = range.start; index < range.end; index += 1) {
      const character = rendered.characters[index];
      if (!character) continue;
      if (character.node !== currentNode) {
        currentNode = character.node;
        currentRange = {
          key: range.key,
          startOffset: character.startOffset,
          endOffset: character.endOffset,
        };
        const nodeRanges = byNode.get(character.node) || [];
        nodeRanges.push(currentRange);
        byNode.set(character.node, nodeRanges);
      } else if (currentRange) {
        currentRange.endOffset = character.endOffset;
      }
    }
  }

  for (const [node, nodeRanges] of byNode) {
    for (const range of nodeRanges.sort((left, right) => right.startOffset - left.startOffset)) {
      const matched = node.splitText(range.startOffset);
      matched.splitText(range.endOffset - range.startOffset);
      const mark = document.createElement("mark");
      mark.className = "wiki-entity-highlight";
      mark.dataset.highlightKey = String(range.key);
      mark.textContent = matched.nodeValue || "";
      matched.parentNode?.replaceChild(mark, matched);
    }
  }
}

function markdownVisibleText(value: string) {
  const withoutDefinitions = value
    .replace(/^\s*\[[^\]]+\]:\s+\S+.*$/gm, " ")
    .replace(/^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/gm, " ");
  const withoutMarkdownLinks = withoutDefinitions
    .replace(/!\[[^\]]*]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)]\([^)]*\)/g, "$1")
    .replace(/<((?:https?|mailto):[^>]+)>/gi, "$1");
  const withoutHtml = withoutMarkdownLinks
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]+>/g, " ");
  const withoutBlockSyntax = withoutHtml
    .replace(/^\s*(```+|~~~+).*$/gm, " ")
    .replace(/^\s{0,3}(?:#{1,6}|>|[-+*]|\d+[.)])\s+/gm, "")
    .replace(/[`*_~]/g, "")
    .replace(/\\([\\`*{}[\]()#+\-.!_>])/g, "$1");
  const decoder = document.createElement("textarea");
  decoder.innerHTML = withoutBlockSyntax;
  return decoder.value;
}

function canonicalCharacters(value: string) {
  return Array.from(value.normalize("NFKC").toLocaleLowerCase())
    .filter((character) => /[\p{L}\p{N}]/u.test(character))
    .join("");
}

function highlightRenderedTermFallback(root: HTMLElement, term: string): HTMLElement | null {
  const matchedTerm = findRenderedTerm(root, term);
  if (!matchedTerm) return null;
  const escaped = escapeRegExp(matchedTerm);
  const pattern = new RegExp(escaped, "gi");
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || !node.nodeValue?.trim()) return NodeFilter.FILTER_REJECT;
      if (parent.closest("code, pre, script, style, textarea, input")) return NodeFilter.FILTER_REJECT;
      if (parent.closest("mark.wiki-entity-highlight")) return NodeFilter.FILTER_REJECT;
      pattern.lastIndex = 0;
      return pattern.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  let firstMark: HTMLElement | null = null;
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
      firstMark ||= mark;
      fragment.append(mark);
      lastIndex = index + match[0].length;
    }
    if (lastIndex < text.length) fragment.append(document.createTextNode(text.slice(lastIndex)));
    node.parentNode?.replaceChild(fragment, node);
  }
  return firstMark;
}

function markdownSection(value: string): { level: number; title: string } | null {
  const heading = value.split("\n").map((line) => line.trim()).find((line) => /^#{1,6}\s+/.test(line));
  if (!heading) return null;
  const match = /^(#{1,6})\s+(.+)$/.exec(heading);
  return match ? { level: match[1].length, title: match[2].replace(/[`*_]/g, "").trim() } : null;
}

function highlightSection(heading: HTMLElement, level: number): HTMLElement | null {
  let current: Element | null = heading;
  while (current) {
    if (current !== heading && /^H[1-6]$/.test(current.tagName) && Number(current.tagName.slice(1)) <= level) break;
    current.classList.add("wiki-evidence-highlight-block");
    current = current.nextElementSibling;
  }
  return heading;
}

function normalizeText(value: string) {
  return value.replace(/\s+/g, " ").trim().toLocaleLowerCase();
}

function findRenderedTerm(root: HTMLElement, term: string): string | null {
  const termLower = term.toLocaleLowerCase();
  const renderedNodes = Array.from(root.querySelectorAll("*:not(script):not(style)"))
    .flatMap((element) => Array.from(element.childNodes))
    .filter((node): node is Text => node.nodeType === Node.TEXT_NODE)
    .map((node) => (node.nodeValue || "").trim())
    .filter((value) => value.length >= 4);
  if (renderedNodes.some((value) => value.toLocaleLowerCase().includes(termLower))) return term;

  const candidates = term
    .split(/[，。；：！？,.;:!?\n]/)
    .map((item) => item.trim())
    .filter((item) => item.length >= 8)
    .sort((left, right) => right.length - left.length);
  const exactCandidate = candidates.find((item) => renderedNodes.some((value) => value.toLocaleLowerCase().includes(item.toLocaleLowerCase())));
  if (exactCandidate) return exactCandidate;

  return renderedNodes
    .filter((value) => termLower.includes(value.toLocaleLowerCase()))
    .sort((left, right) => right.length - left.length)[0] || null;
}

function unwrapEntityHighlights(root: HTMLElement) {
  for (const mark of Array.from(root.querySelectorAll("mark.wiki-entity-highlight"))) {
    mark.replaceWith(document.createTextNode(mark.textContent || ""));
  }
  for (const element of Array.from(root.querySelectorAll(".wiki-evidence-highlight-block"))) {
    element.classList.remove("wiki-evidence-highlight-block");
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
  return content.replace(/\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g, (_match, rawTarget: string, rawAlias: string | undefined, offset: number) => {
    if (offset > 0 && content[offset - 1] === "!") return _match;
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
