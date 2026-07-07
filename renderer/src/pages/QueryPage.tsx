import { useState } from "react";

import { getQueryTrends, searchWiki } from "../api/client";
import type { AppContext } from "../appContext";
import type { QueryResult } from "../api/client";
import { LoadingBlock } from "../components/LoadingBlock";
import { InlineHelp } from "../components/InlineHelp";
import type { VaultOption } from "../vaultRuntime";

type Props = {
  context: AppContext;
  embedded?: boolean;
};

export function QueryPage({ context, embedded = false }: Props) {
  const [query, setQuery] = useState("Agent Loop 控制模式");
  const [queryVaultId, setQueryVaultId] = useState(context.activeVaultId === "all" ? "all" : context.activeVaultId);
  const [pageDirs, setPageDirs] = useState("");
  const [scopedResults, setScopedResults] = useState<ScopedQueryResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const vaultChoices = [
    { id: "all", name: context.t("allVaults") },
    ...context.vaultOptions.filter((vault) => !vault.virtual).map((vault) => ({ id: vault.id, name: vault.name })),
  ];
  const activeQueryVaultId = vaultChoices.some((vault) => vault.id === queryVaultId) ? queryVaultId : "all";

  async function handleSearch() {
    if (isSearching) return;
    if (!query.trim()) {
      context.setNotice({ message: context.t("queryCannotBeEmpty"), error: true });
      return;
    }
    setIsSearching(true);
    context.setNotice(null);
    try {
      const targetVaults = resolveQueryVaults(context.vaultOptions, activeQueryVaultId);
      const pageDirsValue = pageDirs
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const wikiPageDirs = pageDirsValue.length ? pageDirsValue : ["pages"];
      const response = await searchWiki(context.activeVaultSelector, query.trim(), {
        mode: "balanced",
        page_dirs: wikiPageDirs,
        all_vaults: activeQueryVaultId === "all",
        vault_ids: activeQueryVaultId === "all" ? [] : targetVaults.map((vault) => vault.id),
        include_content: true,
        max_context_chars: 200000,
      });
      const nextScopedResults = (response.results || []).map((result) => ({
        vault: vaultForResult(context.vaultOptions, context.activeVaultId, context.vaultPath, result),
        result,
      }));
      setScopedResults(nextScopedResults);
      context.setQueryResults(nextScopedResults.map((item) => item.result));
      context.setQueryContextPack(response.context_pack || "");
      if (targetVaults.some((vault) => vault.id === context.activeVaultId)) {
        const trend = await getQueryTrends(context.activeVaultSelector);
        context.setQueryTrend(trend);
      }
    } catch (error) {
      context.setNotice({ message: error instanceof Error ? error.message : String(error), error: true });
    } finally {
      setIsSearching(false);
    }
  }

  const repeatedGaps = context.queryTrend?.repeated_gap_queries || [];
  const visibleResults = scopedResults.length ? scopedResults : context.queryResults.map((result) => ({
    vault: context.vaultOptions.find((vault) => vault.id === context.activeVaultId) || { id: context.activeVaultId, name: context.activeVaultId, path: context.vaultPath },
    result,
  }));
  const hasQueryResults = visibleResults.length > 0;
  const hasContextPack = Boolean(context.queryContextPack);

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
        <div className="query-controls">
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
          <label className="field">
            <span>{context.t("initialPageDirs")}</span>
            <input value={pageDirs} onChange={(event) => setPageDirs(event.target.value)} placeholder="pages" />
            <small>{context.t("initialPageDirsHint")}</small>
          </label>
        </div>
        <div className="query-health">
          <article>
            <span>{context.t("queryTrendSample")}</span>
            <strong>{context.queryTrend?.sample_size ?? 0}</strong>
          </article>
          <article>
            <span>{context.t("queryNoResultCount")}</span>
            <strong>{context.queryTrend?.no_result_count ?? 0}</strong>
          </article>
          <article>
            <span>{context.t("queryLowConfidenceCount")}</span>
            <strong>{context.queryTrend?.low_confidence_count ?? 0}</strong>
          </article>
        </div>
        {!!repeatedGaps.length && (
          <aside className="query-gap-panel">
            <h3>{context.t("repeatedQueryGaps")}</h3>
            <p>{context.t("repeatedQueryGapsCopy")}</p>
            <div className="query-gap-list">
              {repeatedGaps.map((item) => (
                <span key={item.query}>
                  {item.query} <strong>{item.count}</strong>
                </span>
              ))}
            </div>
          </aside>
        )}
        <div className="result-list" aria-busy={isSearching}>
          {isSearching ? (
            <LoadingBlock title={context.t("querySearching")} copy={context.t("querySearchingCopy")} />
          ) : hasQueryResults ? (
            visibleResults.map(({ vault, result }) => (
              <article className="result-item" key={`${vault.id}:${result.path}`}>
                <div className="result-item-header">
                  <h3>{result.title || result.path}</h3>
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
                <div className="result-meta">
                  <span className="origin-badge vault-origin">{context.t("sourceVault")}: {vault.name}</span>
                  <span className={`origin-badge ${result.match_kind === "related" ? "related" : "direct"}`}>
                    {result.match_kind === "related" ? context.t("relatedContext") : context.t("directMatch")}
                  </span>
                  <span>{result.path}</span>
                  <span>{result.relevance}</span>
                  <span>{context.t("score")} {Number(result.score || 0).toFixed(1)}</span>
                  <span>{context.t("matched")} {(result.matched_fields || []).join(", ") || context.t("unknown")}</span>
                </div>
                {result.reason && <p className="result-reason">{result.reason}</p>}
                <p>{result.summary || context.t("noSummary")}</p>
                {!!result.claims?.length && (
                  <ul className="compact-list">
                    {result.claims.slice(0, 3).map((point) => (
                      <li key={point}>{point}</li>
                    ))}
                  </ul>
                )}
                {!!result.excerpts?.length && (
                  <details>
                    <summary>{context.t("excerpts")}</summary>
                    {result.excerpts.slice(0, 2).map((excerpt) => (
                      <blockquote key={`${result.path}:${excerpt.heading}:${excerpt.score}`}>
                        <strong>{excerpt.heading || context.t("excerpt")}</strong>
                        <p>{excerpt.content}</p>
                      </blockquote>
                    ))}
                  </details>
                )}
              </article>
            ))
          ) : null}
        </div>
      </article>
      <article className="panel">
        <div className="panel-header">
          <div>
            <h2>
              {context.t("contextPack")}
              <InlineHelp text={context.t("contextPackCopy")} />
            </h2>
          </div>
          <button className="button secondary" onClick={() => void navigator.clipboard?.writeText(context.queryContextPack || "")}>
            {context.t("copy")}
          </button>
        </div>
        {isSearching ? (
          <LoadingBlock title={context.t("queryContextBuilding")} copy={context.t("queryContextBuildingCopy")} compact />
        ) : (
          <pre className={`output light ${hasContextPack ? "" : "output-empty"}`}>{context.queryContextPack || context.t("runSearchForContext")}</pre>
        )}
      </article>
    </section>
  );
}

type ScopedQueryResult = {
  vault: VaultOption;
  result: QueryResult;
};

function resolveQueryVaults(
  vaults: VaultOption[],
  queryVaultId: string,
) {
  const concreteVaults = vaults.filter((vault) => !vault.virtual);
  if (queryVaultId === "all") return concreteVaults;
  const current = concreteVaults.filter((vault) => vault.id === queryVaultId);
  return current.length ? current : concreteVaults.slice(0, 1);
}

function openResultPage(context: AppContext, vault: VaultOption, path: string) {
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

function openResultGraph(context: AppContext, vault: VaultOption, path: string) {
  context.setActiveVaultId(vault.id);
  context.openPageInGraph(path);
}

function askAboutResult(context: AppContext, vault: VaultOption, result: QueryResult) {
  const title = result.title || result.path;
  context.openChatWithPrompt(`请解释「${title}」（${result.path}），并说明它和我当前问题的关系。`, vault.id);
}
