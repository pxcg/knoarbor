import { requestJson } from "./http";
import { selectorToBody, singleVaultQuery } from "./scope";
import type { PageDetail, PageRelation, PageSummary, ProjectionEdit, RawRevisionEdit, VaultSelector, WorkflowResponse } from "./types";

export type PageDeleteResponse = {
  deleted: boolean;
  path: string;
};

export async function getPages(selector: VaultSelector): Promise<{ vault_path: string; pages: PageSummary[] }> {
  return requestJson(`/wiki/pages?${singleVaultQuery(selector)}`);
}

export async function getPage(selector: VaultSelector, path: string): Promise<PageDetail> {
  return requestJson(`/wiki/pages/content?${singleVaultQuery(selector)}&path=${encodeURIComponent(path)}`);
}

export async function getPageRelations(selector: VaultSelector, path: string): Promise<{ path: string; outgoing_pages: PageRelation[]; incoming_pages: PageRelation[] }> {
  return requestJson(`/wiki/pages/relations?${singleVaultQuery(selector)}&path=${encodeURIComponent(path)}`);
}

export async function updatePage(selector: VaultSelector, path: string, edit: ProjectionEdit): Promise<PageDetail> {
  return requestJson("/wiki/pages/content", {
    method: "PATCH",
    body: { path, edit, ...selectorToBody(selector) },
  });
}

export async function updateRawPage(selector: VaultSelector, path: string, edit: RawRevisionEdit): Promise<WorkflowResponse> {
  return requestJson("/wiki/pages/raw", {
    method: "PATCH",
    body: { path, edit, ...selectorToBody(selector) },
  });
}

export async function deletePage(selector: VaultSelector, path: string): Promise<PageDeleteResponse> {
  return requestJson("/wiki/pages/content", {
    method: "DELETE",
    body: { path, ...selectorToBody(selector) },
  });
}

