import { useState } from "react";

import { searchWiki } from "../api/client";
import type { QueryAppContext } from "../appContext";
import type { QueryRawEvidence, QueryResult, QuerySearchResponse } from "../api/client";
import { LoadingBlock } from "../components/LoadingBlock";
import { InlineHelp } from "../components/InlineHelp";
import type { VaultOption } from "../vaultRuntime";

type Props = {
  context: QueryAppContext;
  embedded?: boolean;
};

export function QueryPage({ context, embedded = false }: Props) {
  const [query, setQuery] = useState("");
  const [queryVaultId, setQueryVaultId] = useState(context.activeVaultId === "all" ? "all" : context.activeVaultId);
  const [scopedResults, setScopedResults] = useState<ScopedQueryResult[]>([]);
  const [queryResponse, setQueryResponse] = useState<QuerySearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const vaultChoices = [
    { id: "all", name: context.t("allVaults") },
    ...context.vaultOptions.filter((vault) => !vault.virtual).map((vault) => ({ id: vault.id, name: vault.name })),
  ];
  const activeQueryVaultId = vaultChoices.some((vault) => vault.id === queryVaultId) ? queryVaultId : "all";

  async function handleSearch() {
    if (isSearching) return;
    if (!query.trim()) {
      return;
    }
    setIsSearching(true);
    try {
      const targetVaults = resolveQueryVaults(context.vaultOptions, activeQueryVaultId);
      const response = await searchWiki(context.activeVaultSelector, query.trim(), {
        all_vaults: activeQueryVaultId === "all",
        vault_ids: activeQueryVaultId === "all" ? [] : targetVaults.map((vault) => vault.id),
      });
      const nextScopedResults = (response.results || []).map((result) => ({
        vault: vaultForResult(context.vaultOptions, context.activeVaultId, context.vaultPath, result),
        result,
      }));
      setScopedResults(nextScopedResults);
      setQueryResponse(response);
    } catch (error) {
      console.error("Knowledge query failed", error);
    } finally {
      setIsSearching(false);
    }
  }

  const visibleResults = scopedResults;
  const hasQueryResults = visibleResults.length > 0;
  const rawEvidence = queryResponse?.raw_evidence || [];

  return (
    <section className={embedded ? "embedded-section" : "view active"}>
      <article className="panel">
        <div className="panel-header">
          <div>
            <h2>
              {context.t("queryTitle")}
              <InlineHelp text={context.t("querySubtitle")} />
            </h2>
          </div>
          <button className="button primary" onClick={handleSearch} disabled={isSearching}>
            {isSearching ? context.t("querySearching") : context.t("search")}
          </button>
        </div>
        <label className="field">
          <span>{context.t("questionOrTopic")}</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <div className="query-controls query-controls-single">
          <div className="field">
            <span>{context.t("queryVaultScope")}</span>
            <div className="query-vault-switcher" role="radiogroup" aria-label={context.t("queryVaultScope")}>
              {vaultChoices.map((vault) => (
                <button
                  aria-checked={activeQueryVaultId === vault.id}
                  className={`query-vault-option ${activeQueryVaultId === vault.id ? "active" : ""}`}
                  key={vault.id}
                  onClick={() => setQueryVaultId(vault.id)}
                  role="radio"
                  type="button"
                >
                  {vault.name}
                </button>
              ))}
            </div>
            <small>{context.t("queryAcrossVaults")}</small>
          </div>
        </div>
        <div className="result-list" aria-busy={isSearching}>
          {isSearching ? (
            <LoadingBlock title={context.t("querySearching")} copy={context.t("querySearchingCopy")} />
          ) : hasQueryResults ? (
            visibleResults.map(({ vault, result }) => (
              <article className="result-item" key={`${vault.id}:${result.path}`}>
                <div className="result-item-header">
                  <h3>{queryResultTitle(result, rawEvidence)}</h3>
                  <div className="button-row compact-row">
                    <button className="button secondary small-button" type="button" onClick={() => openResultPage(context, vault, result.path)}>
                      {context.t("openInWiki")}
                    </button>
                    <button className="button secondary small-button" type="button" onClick={() => askAboutResult(context, vault, result)}>
                      {context.t("askInChat")}
                    </button>
                    <button className="button secondary small-button" type="button" onClick={() => openResultGraph(context, vault, result.path)}>
                      {context.t("openInGraph")}
                    </button>
                  </div>
                </div>
                <div className="result-meta query-result-meta">
                  <span className="origin-badge vault-origin">{context.t("sourceVault")}: {vault.name}</span>
                </div>
                <p>{result.reason}</p>
              </article>
            ))
          ) : null}
        </div>
      </article>
      <article className="panel">
        <div className="panel-header">
          <div>
            <h2>
              {context.t("rawEvidence")}
              <InlineHelp text={context.t("rawEvidenceCopy")} />
            </h2>
          </div>
        </div>
        {isSearching ? (
          <LoadingBlock title={context.t("queryContextBuilding")} copy={context.t("queryContextBuildingCopy")} compact />
        ) : rawEvidence.length ? (
          <div className="raw-evidence-list">
            {rawEvidence.map((item) => (
              <RawEvidenceCard item={item} key={item.evidence_id} context={context} />
            ))}
          </div>
        ) : (
          <div className="raw-evidence-empty">
            <strong>{context.t("rawEvidenceEmpty")}</strong>
            <p>{context.t("rawEvidenceEmptyCopy")}</p>
          </div>
        )}
      </article>
    </section>
  );
}

type ScopedQueryResult = {
  vault: VaultOption;
  result: QueryResult;
};

function RawEvidenceCard({ item, context }: { item: QueryRawEvidence; context: QueryAppContext }) {
  const title = item.title || item.source_path || item.source_unit_id;
  return (
    <article className="raw-evidence-card">
      <div className="raw-evidence-card-header">
        <h3>{title}</h3>
        <span className={`origin-badge ${item.relevance || "medium"}`}>{item.relevance || context.t("unknown")}</span>
      </div>
      <blockquote>
        <p>{item.content || item.excerpt}</p>
      </blockquote>
    </article>
  );
}

function queryResultTitle(result: QueryResult, evidence: QueryRawEvidence[]): string {
  const source = evidence.find((item) => item.locator_page_paths?.includes(result.path));
  return source?.title || result.title || result.path;
}

function resolveQueryVaults(
  vaults: VaultOption[],
  queryVaultId: string,
) {
  const concreteVaults = vaults.filter((vault) => !vault.virtual);
  if (queryVaultId === "all") return concreteVaults;
  const current = concreteVaults.filter((vault) => vault.id === queryVaultId);
  return current.length ? current : concreteVaults.slice(0, 1);
}

function openResultPage(context: QueryAppContext, vault: VaultOption, path: string) {
  context.openWikiPageInVault(vault.id, path);
}

function vaultForResult(vaults: VaultOption[], activeVaultId: string, activeVaultPath: string, result: QueryResult): VaultOption {
  const byId = result.vault_id ? vaults.find((vault) => vault.id === result.vault_id) : null;
  if (byId) return byId;
  const byPath = result.vault_path ? vaults.find((vault) => vault.path === result.vault_path) : null;
  if (byPath) return byPath;
  return vaults.find((vault) => vault.id === activeVaultId) || {
    id: activeVaultId,
    name: result.vault_name || activeVaultId,
    path: activeVaultPath,
  };
}

function openResultGraph(context: QueryAppContext, vault: VaultOption, path: string) {
  context.openPageInGraph(path, vault.id);
}

function askAboutResult(context: QueryAppContext, vault: VaultOption, result: QueryResult) {
  const title = result.title || result.path;
  context.openChatWithPrompt(`请解释「${title}」（${result.path}），并说明它和我当前问题的关系。`, vault.id);
}
