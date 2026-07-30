import type { PageDetail } from "../../api/client";
import type { WikiAppContext } from "../../appContext";
import { AsyncMarkdownPreview } from "../../components/AsyncMarkdownPreview";
import {
  extractWikiSections,
  orderWikiSections,
  parseMarkdownTable,
  parseProjectionClaims,
  plainCellText,
  wikiSectionLabel,
  type WikiSection,
} from "./WikiModel";

export function WikiStructuredPreview({
  detail,
  context,
  highlightTerm,
  onHighlightTerm,
  onOpenEvidence,
}: {
  detail: PageDetail;
  context: WikiAppContext;
  highlightTerm?: string | null;
  onHighlightTerm?: (term: string) => void;
  onOpenEvidence?: (term: string) => void;
}) {
  const sections = extractWikiSections(detail.content);
  if (!sections.length) {
    return (
      <AsyncMarkdownPreview
        content={detail.content}
        className="wiki-markdown-preview"
        stripFrontmatter
        onOpenWikiPage={context.openWikiPage}
        vaultPath={context.vaultPath}
        highlightTerm={highlightTerm}
        onHighlightTerm={onHighlightTerm}
      />
    );
  }
  const ordered = orderWikiSections(sections).filter((section) => section.key !== "source");
  return (
    <div className="wiki-structured-preview">
      {ordered.map((section) => (
        <section className={`wiki-structure-card wiki-structure-${section.key}`} key={section.key}>
          <div className="wiki-structure-heading">
            <span>{wikiSectionLabel(section.key, section.title, context.language)}</span>
          </div>
          <WikiSectionContent section={section} context={context} highlightTerm={highlightTerm} onHighlightTerm={onHighlightTerm} onOpenEvidence={onOpenEvidence} />
        </section>
      ))}
    </div>
  );
}

function WikiSectionContent({
  section,
  context,
  highlightTerm,
  onHighlightTerm,
  onOpenEvidence,
}: {
  section: WikiSection;
  context: WikiAppContext;
  highlightTerm?: string | null;
  onHighlightTerm?: (term: string) => void;
  onOpenEvidence?: (term: string) => void;
}) {
  if (section.key === "claims") {
    const claims = parseProjectionClaims(section.content);
    if (claims.length) {
      return (
        <div className="wiki-claim-list">
          {claims.map((claim) => (
            <article className="wiki-claim" key={claim.id}>
              <span className="wiki-claim-id">{claim.id}</span>
              <AsyncMarkdownPreview content={claim.statement} className="wiki-section-markdown" />
              {claim.evidence && onOpenEvidence ? (
                <details className="wiki-claim-evidence">
                  <summary title={context.t("wikiClaimEvidence")} aria-label={context.t("wikiClaimEvidence")}>▸</summary>
                  <button
                    className="wiki-claim-evidence-card"
                    type="button"
                    onClick={() => onOpenEvidence(evidenceHighlightTerm(claim.evidence))}
                  >
                    <AsyncMarkdownPreview content={evidencePreview(claim.evidence)} className="wiki-section-markdown" />
                  </button>
                </details>
              ) : null}
            </article>
          ))}
        </div>
      );
    }
  }
  if (section.key === "relations" || section.key === "evidence" || section.key === "attachments") {
    const table = parseMarkdownTable(section.content);
    if (table) {
      return (
        <div className={`wiki-structured-table-wrap wiki-${section.key}-table-wrap`}>
          <table className={`wiki-structured-table wiki-${section.key}-table`}>
            <thead>
              <tr>
                {table.headers.map((header) => <th key={header}>{plainCellText(header)}</th>)}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, rowIndex) => (
                <tr key={`${section.key}-${rowIndex}`}>
                  {table.headers.map((_header, cellIndex) => (
                    <td key={cellIndex}>{plainCellText(row[cellIndex] || "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
  }
  return (
    <AsyncMarkdownPreview
      content={section.content}
      className="wiki-markdown-preview wiki-section-markdown"
      onOpenWikiPage={context.openWikiPage}
      vaultPath={context.vaultPath}
      highlightTerm={highlightTerm}
      onHighlightTerm={onHighlightTerm}
    />
  );
}

function evidenceHighlightTerm(evidence: string) {
  return evidencePreview(evidence);
}

function evidencePreview(evidence: string) {
  return evidence
    .split("\n")
    .filter((line) => !line.trim().startsWith("Source:"))
    .map((line) => line.replace(/^\s*>\s?/, ""))
    .join("\n")
    .trim();
}
