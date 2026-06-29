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
  if (section.key === "attachments") {
    const table = parseMarkdownTable(section.content);
    if (table) return <AttachmentCards table={table} />;
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
    />
  );
}

function AttachmentCards({ table }: { table: NonNullable<ReturnType<typeof parseMarkdownTable>> }) {
  const headers = table.headers.map((header) => plainCellText(header).toLowerCase());
  const topicIndex = findHeader(headers, ["topic", "name", "title", "主题", "名称"]);
  const descriptionIndex = findHeader(headers, ["description", "summary", "caption", "描述", "说明"]);
  const pathIndex = findHeader(headers, ["path", "路径"]);

  return (
    <div className="wiki-attachment-list">
      {table.rows.map((row, index) => {
        const rawTopic = plainCellText(row[topicIndex] || "");
        const path = plainCellText(row[pathIndex] || "");
        const topic = readableAttachmentTopic(rawTopic, path, index);
        const description = plainCellText(row[descriptionIndex] || "");
        return (
          <article className="wiki-attachment-card" key={`${topic}-${index}`}>
            <strong>{topic}</strong>
            <p>{description || "该附件保留为资料图像，当前页面未生成额外说明。"}</p>
          </article>
        );
      })}
    </div>
  );
}

function findHeader(headers: string[], candidates: string[]) {
  const index = headers.findIndex((header) => candidates.some((candidate) => header.includes(candidate.toLowerCase())));
  return index >= 0 ? index : 0;
}

function readableAttachmentTopic(topic: string, path: string, index: number) {
  const value = topic || path;
  const fileName = value.split(/[\\/]/).filter(Boolean).pop() || "";
  const stem = fileName.replace(/\.[a-z0-9]+$/i, "");
  if (!stem || /^[a-f0-9]{24,}$/i.test(stem)) return `附件 ${index + 1}`;
  return stem;
}
