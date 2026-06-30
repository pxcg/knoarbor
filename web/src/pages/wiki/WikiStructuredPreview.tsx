import type { PageDetail } from "../../api/client";
import type { AppContext } from "../../appContext";
import { AsyncMarkdownPreview } from "../../components/AsyncMarkdownPreview";
import {
  extractWikiSections,
  orderWikiSections,
  parseMarkdownTable,
  plainCellText,
  wikiSectionLabel,
  type WikiSection,
} from "./WikiModel";

export function WikiStructuredPreview({ detail, context }: { detail: PageDetail; context: AppContext }) {
  const sections = extractWikiSections(detail.content);
  if (!sections.length) {
    return <AsyncMarkdownPreview content={detail.content} className="wiki-markdown-preview" stripFrontmatter onOpenWikiPage={context.openWikiPage} vaultPath={context.vaultPath} />;
  }
  const ordered = orderWikiSections(sections);
  return (
    <div className="wiki-structured-preview">
      {ordered.map((section) => (
        <section className={`wiki-structure-card wiki-structure-${section.key}`} key={section.key}>
          <div className="wiki-structure-heading">
            <span>{wikiSectionLabel(section.key, section.title, context.language)}</span>
          </div>
          <WikiSectionContent section={section} context={context} />
        </section>
      ))}
    </div>
  );
}

function WikiSectionContent({ section, context }: { section: WikiSection; context: AppContext }) {
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
    />
  );
}
