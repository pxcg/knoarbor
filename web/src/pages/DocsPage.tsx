import { useEffect, useMemo, useState } from "react";

import { getProjectDoc } from "../api/client";
import type { AppContext } from "../App";
import { AsyncMarkdownPreview } from "../components/AsyncMarkdownPreview";
import { LoadingBlock } from "../components/LoadingBlock";

type Props = {
  context: AppContext;
};

type DocItem = {
  path: string;
  titleKey: string;
  subtitleKey: string;
};

type DocGroup = {
  titleKey: string;
  items: DocItem[];
};

const docGroups: DocGroup[] = [
  {
    titleKey: "docOverviewGroup",
    items: [
      { path: "README.md", titleKey: "docReadme", subtitleKey: "docReadmeCopy" },
      { path: "SHOWCASE.md", titleKey: "docShowcase", subtitleKey: "docShowcaseCopy" },
      { path: "QUICKSTART.md", titleKey: "docQuickstart", subtitleKey: "docQuickstartCopy" },
      { path: "CONCEPTS.md", titleKey: "docConcepts", subtitleKey: "docConceptsCopy" },
    ],
  },
  {
    titleKey: "docOperateGroup",
    items: [
      { path: "CONFIGURATION.md", titleKey: "docConfiguration", subtitleKey: "docConfigurationCopy" },
      { path: "CLI.md", titleKey: "docCli", subtitleKey: "docCliCopy" },
      { path: "API.md", titleKey: "docApi", subtitleKey: "docApiCopy" },
    ],
  },
  {
    titleKey: "docDesignGroup",
    items: [
      { path: "ARCHITECTURE.md", titleKey: "docArchitecture", subtitleKey: "docArchitectureCopy" },
      { path: "PROVENANCE_DESIGN.md", titleKey: "docProvenance", subtitleKey: "docProvenanceCopy" },
    ],
  },
  {
    titleKey: "docReferenceGroup",
    items: [
      { path: "ERROR_CODES.md", titleKey: "docErrorCodes", subtitleKey: "docErrorCodesCopy" },
      { path: "DEVELOPMENT.md", titleKey: "docDevelopment", subtitleKey: "docDevelopmentCopy" },
    ],
  },
];

export function DocsPage({ context }: Props) {
  const [selectedPath, setSelectedPath] = useState("QUICKSTART.md");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);

  const selectedDoc = useMemo(
    () => docGroups.flatMap((group) => group.items).find((item) => item.path === selectedPath),
    [selectedPath],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const localizedPath = context.language === "zh" ? `zh/${selectedPath}` : selectedPath;
    const request = getProjectDoc(localizedPath).catch((error) => {
      if (localizedPath !== selectedPath) return getProjectDoc(selectedPath);
      throw error;
    });
    request
      .then((doc) => {
        if (!cancelled) setContent(doc.content);
      })
      .catch((error) => {
        if (!cancelled) context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [context, context.language, selectedPath]);

  return (
    <section className="view active">
      <div className="docs-workspace">
        <aside className="panel docs-directory">
          <div className="panel-header compact">
            <h2>{context.t("docsDirectory")}</h2>
          </div>
          {docGroups.map((group) => (
            <section className="docs-group" key={group.titleKey}>
              <h3>{context.t(group.titleKey)}</h3>
              <div className="docs-link-list">
                {group.items.map((item) => (
                  <button
                    className={`docs-link ${selectedPath === item.path ? "active" : ""}`}
                    key={item.path}
                    onClick={() => setSelectedPath(item.path)}
                    type="button"
                  >
                    <strong>{context.t(item.titleKey)}</strong>
                    <span>{context.t(item.subtitleKey)}</span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </aside>

        <article className="panel docs-preview-panel">
          <div className="panel-header">
            <div>
              <h2>{selectedDoc ? context.t(selectedDoc.titleKey) : selectedPath}</h2>
              <p className="panel-copy">{selectedPath}</p>
            </div>
          </div>
          {loading ? (
            <LoadingBlock title={context.t("docsLoading")} copy={context.t("docsLoadingCopy")} />
          ) : (
            <AsyncMarkdownPreview content={content} currentDocPath={selectedPath} onOpenDocLink={setSelectedPath} />
          )}
        </article>
      </div>
    </section>
  );
}
