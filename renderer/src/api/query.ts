import { requestJson } from "./http";
import { singleVaultQuery } from "./scope";
import type { QuerySearchResponse, QueryTrendResponse, VaultSelector } from "./types";

export type QuerySearchOptions = {
  vault_ids?: string[];
  all_vaults?: boolean;
  continuation_cursor?: string;
  continuation_cursors?: Record<string, string>;
};

export async function searchWiki(selector: VaultSelector, query: string, options: QuerySearchOptions = {}): Promise<QuerySearchResponse> {
  return requestJson("/query", {
    method: "POST",
    body: {
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      query,
      vault_ids: options.vault_ids || [],
      all_vaults: options.all_vaults || false,
      continuation_cursor: options.continuation_cursor,
      continuation_cursors: options.continuation_cursors || {},
    },
  });
}

export async function sendQueryFeedback(
  selector: VaultSelector,
  body: { query: string; useful?: boolean | null; selected_paths?: string[]; rejected_paths?: string[]; comment?: string },
): Promise<{ recorded: boolean; ledger_path: string }> {
  return requestJson("/query/feedback", {
    method: "POST",
    body: {
      config_path: selector.config_path,
      vault_id: selector.vault_id,
      vault_path: selector.vault_id ? undefined : selector.vault_path,
      query: body.query,
      useful: body.useful ?? null,
      selected_paths: body.selected_paths || [],
      rejected_paths: body.rejected_paths || [],
      comment: body.comment || "",
      caller: "web",
    },
  });
}

export async function getQueryTrends(selector: VaultSelector, limit = 100): Promise<QueryTrendResponse> {
  return requestJson(`/query/trends?${singleVaultQuery(selector)}&limit=${limit}`);
}

