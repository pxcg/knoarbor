import { expect, test } from "@playwright/test";
import type { ChatAppContext } from "../../src/appContext";
import { listAllChatSessions, resolveChatCitations } from "../../src/api/client";
import { extractWikiPagePaths, parseReportArtifacts } from "../../src/components/report/reportParser";
import { openCitationTarget } from "../../src/pages/chat/ChatEvidence";
import { evidenceForCitation, type ChatTurn } from "../../src/pages/chat/ChatModel";
import { turnCanBeIngested } from "../../src/pages/chat/useChatSelectionIngest";
import { pageVaultStorageKey } from "../../src/appNavigation";
import { readableLaunchError, workflowRunIdentity } from "../../src/pages/run/useRunLauncher";
import { ingestPreparation } from "../../src/pages/run/useRunLauncher";
import { flowStages, isMaterializationPending, isTerminalRunStatus } from "../../src/components/runs/RunPanelModel";
import { isApiNotFound, requestJson } from "../../src/api/http";
import { userFacingError } from "../../src/userFacingError";
import { resolveVaultAssetImageSrc } from "../../src/vaultAssetPaths";

test("projection image paths resolve through the active vault asset endpoint", () => {
  expect(resolveVaultAssetImageSrc(
    "../../raw/derived/assets/images/figure.jpg",
    "/Users/test/KnoArbor-Vault",
  )).toBe("/vault-assets/images%2Ffigure.jpg?vault_path=%2FUsers%2Ftest%2FKnoArbor-Vault");
});

test("local ingest exposes document preprocessing before a run record exists", () => {
  expect(ingestPreparation("file", "/tmp/report.pdf")).toEqual({
    inputPath: "/tmp/report.pdf",
    kind: "document",
  });
  expect(ingestPreparation("file", "/tmp/note.md")).toBeNull();
  expect(ingestPreparation("folder", "/tmp/reports")?.kind).toBe("folder");
  expect(ingestPreparation("codex", "")).toBeNull();
});

test("terminal ingest runs leave the active progress surface", () => {
  expect(isTerminalRunStatus("completed")).toBe(true);
  expect(isTerminalRunStatus("failed")).toBe(true);
  expect(isTerminalRunStatus("cancelled")).toBe(true);
  expect(isTerminalRunStatus("partially_failed")).toBe(true);
  expect(isTerminalRunStatus("queued")).toBe(false);
  expect(isTerminalRunStatus("running")).toBe(false);
  expect(isTerminalRunStatus("waiting_model")).toBe(false);
});

test("queued ingest registration retains the run identity needed for terminal refresh", () => {
  expect(workflowRunIdentity({
    run_id: "run_fast",
    run: { vault_id: "personal", status: "queued" },
  })).toEqual({ runId: "run_fast", vaultId: "personal" });
  expect(workflowRunIdentity({ status: "queued" })).toBeNull();
});

test("page deletion feedback requires an authoritative backend 404", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    error: {
      code: "KA-INPUT-002",
      category: "user_input_error",
      message: "Vault file not found: Missing.md",
    },
  }), {
    status: 404,
    headers: { "Content-Type": "application/json" },
  });
  try {
    let error: unknown;
    try {
      await requestJson("/wiki/pages/content");
    } catch (caught) {
      error = caught;
    }
    expect(isApiNotFound(error)).toBe(true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("materialization pending is a distinct ingest terminal condition", () => {
  const run = {
    run_id: "run_pending",
    flow: "ingest",
    status: "completed",
    result_summary: { materialization_pending: true },
  };
  expect(isMaterializationPending(run as never)).toBe(true);
  expect(isMaterializationPending({ ...run, result_summary: {} } as never)).toBe(false);
  expect(isMaterializationPending({ ...run, flow: "lint" } as never)).toBe(false);
  expect(userFacingError(new Error("Knowledge view materialization is pending"), "zh"))
    .toContain("知识库视图正在等待刷新");
});

test("ingest progress exposes compiler validation without the retired quality gate", () => {
  const stageKeys = flowStages("ingest").map((stage) => stage.key);
  expect(stageKeys).toContain("index_metadata_validation");
  expect(stageKeys).not.toContain("quality_gate");
});

test("completed chat text remains user-curatable regardless of answer provenance", () => {
  const assistantTurn = (mode: NonNullable<ChatTurn["answerProvenance"]>["mode"]): ChatTurn => ({
    role: "assistant",
    content: "User-selected material.",
    kind: "answer",
    answerProvenance: {
      mode,
      query_outcome: mode === "general_knowledge" ? "no_match" : "not_applicable",
      chat_outcome: mode === "general_knowledge" ? "no_match" : "direct",
    },
  });

  expect(turnCanBeIngested(assistantTurn("knowledge_grounded"))).toBe(true);
  expect(turnCanBeIngested(assistantTurn("general_knowledge"))).toBe(true);
  expect(turnCanBeIngested(assistantTurn("direct_capability"))).toBe(true);
  expect(turnCanBeIngested({ role: "user", content: "User note." })).toBe(true);
  expect(turnCanBeIngested({ role: "assistant", content: "", kind: "answer" })).toBe(false);
  expect(turnCanBeIngested({ role: "assistant", content: "Pending", streaming: true })).toBe(false);
  expect(turnCanBeIngested({ role: "assistant", content: "Failure", kind: "error" })).toBe(false);
  expect(turnCanBeIngested({ role: "assistant", content: "Working", kind: "status" })).toBe(false);
});

test("persisted citations resolve temporary highlight text without adding Raw to the session", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, unknown> | null = null;
  globalThis.fetch = async (_input, init) => {
    requestBody = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
    return new Response(JSON.stringify({
      schema_version: "chat_citation_resolve_response.v1",
      resolutions: [{
        index: 0,
        status: "resolved",
        text: "Technology advances should be monitored and deployed.",
        texts: ["Technology advances should be monitored and deployed."],
      }],
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  const citation = {
    kind: "raw_evidence" as const,
    evidence_id: "evh:nist",
    raw_revision_id: "rawrev:nist",
    source_unit_id: "unit:nist-appendix",
    char_start: 41,
    char_end: 97,
  };

  try {
    const result = await resolveChatCitations({ vault_id: "six-docs" }, [citation]);
    expect(result.resolutions[0].text).toBe("Technology advances should be monitored and deployed.");
    expect(requestBody).toEqual({
      schema_version: "chat_citation_resolve_request.v1",
      vault_id: "six-docs",
      citations: [citation],
    });
    expect(JSON.stringify(citation)).not.toContain("Technology advances");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("each non-chat page persists an independent knowledge-base selection", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(({ wikiKey, tokenKey }) => {
    localStorage.setItem(wikiKey, "wiki-vault");
    localStorage.setItem(tokenKey, "token-vault");
  }, { wikiKey: pageVaultStorageKey("wiki"), tokenKey: pageVaultStorageKey("tokens") });
  expect(await page.evaluate((key) => localStorage.getItem(key), pageVaultStorageKey("wiki"))).toBe("wiki-vault");
  expect(await page.evaluate((key) => localStorage.getItem(key), pageVaultStorageKey("tokens"))).toBe("token-vault");
  expect(pageVaultStorageKey("wiki")).not.toBe(pageVaultStorageKey("tokens"));
});

test("workflow launch errors are translated without leaking backend detail", () => {
  const context = { t: (key: string) => key };
  expect(readableLaunchError(new Error("API key missing at /private/config.yaml"), context as never))
    .toBe("workflowModelConfigurationError");
  expect(readableLaunchError(new Error("unexpected backend traceback"), context as never))
    .toBe("workflowLaunchError");
});

test("citation preview prefers the exact evidence span over a shared source unit", () => {
  const shared = {
    raw_record_id: "raw:aurora",
    raw_revision_id: "rawrev:aurora",
    source_unit_id: "unit:aurora",
    source_record_id: "source:aurora",
    source_path: "raw/aurora.md",
    unit_index: 0,
    unit_type: "excerpt",
    title: "Aurora",
    content: "Distribution sentence. Observation locations sentence.",
    structural_path: [],
    locator_atom_ids: [],
    locator_page_paths: ["aurora.md"],
  };
  const evidence = [
    { ...shared, evidence_id: "evref:distribution", excerpt: "Distribution sentence." },
    { ...shared, evidence_id: "evref:locations", excerpt: "Observation locations sentence." },
  ];

  expect(evidenceForCitation({ kind: "source", evidence_id: "evref:locations", source_unit_id: "unit:aurora" }, evidence)?.excerpt)
    .toBe("Observation locations sentence.");
  expect(evidenceForCitation({ kind: "source", source_unit_id: "unit:aurora" }, evidence)?.excerpt)
    .toBe("Distribution sentence.");
});

test("chat session pagination loads summaries beyond the first page", async () => {
  const originalFetch = globalThis.fetch;
  const offsets: number[] = [];
  globalThis.fetch = async (input) => {
    const url = new URL(String(input), "http://localhost");
    const offset = Number(url.searchParams.get("offset") || "0");
    offsets.push(offset);
    const sessions = offset === 0
      ? [
          { session_id: "chat_3", title: "Newest", updated_at: "2026-07-24T03:00:00Z" },
          { session_id: "chat_2", title: "Middle", updated_at: "2026-07-24T02:00:00Z" },
        ]
      : [
          { session_id: "chat_1", title: "Oldest", updated_at: "2026-07-24T01:00:00Z" },
        ];
    return new Response(JSON.stringify({
      sessions,
      total_count: 3,
      offset,
      limit: 2,
      has_more: offset === 0,
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  try {
    const result = await listAllChatSessions({ vault_id: "test" }, 2);
    expect(result.sessions.map((session) => session.session_id)).toEqual([
      "chat_3",
      "chat_2",
      "chat_1",
    ]);
    expect(offsets).toEqual([0, 2]);
    expect(result.has_more).toBe(false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("report parser preserves localized page paths", () => {
  const localizedPath = "北极光的形成与观测--43e56a922050.md";
  const report = [
    "Generated pages:",
    `- ${localizedPath}`,
    "",
    "Scoped lint pages:",
    `- ${localizedPath}`,
  ].join("\n");

  expect(extractWikiPagePaths(`- ${localizedPath}`)).toEqual([localizedPath]);
  expect(extractWikiPagePaths("- A title with spaces--abc123.md")).toEqual(["A title with spaces--abc123.md"]);
  expect(extractWikiPagePaths("Created `sources/manual/input.md` successfully.")).toEqual(["sources/manual/input.md"]);
  expect(parseReportArtifacts(report).writtenPages.map((artifact) => artifact.path)).toEqual([localizedPath]);
});

test("run citation resolves and opens the exact persisted run identity", async () => {
  const originalFetch = globalThis.fetch;
  const opened: Array<{ runId: string; vaultId: string; flow: string }> = [];
  globalThis.fetch = async (input) => {
    expect(String(input)).toContain("/runs/run_chat_ingest?");
    expect(String(input)).toContain("vault_id=work");
    return new Response(JSON.stringify({ run_id: "run_chat_ingest", vault_id: "work", flow: "ingest", status: "succeeded" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  const context = {
    activeVaultId: "personal",
    chatScopeVaultSelector: { config_path: "/tmp/config.yaml", vault_id: "all" },
    openRun: (runId: string, vaultId: string, flow: string) => opened.push({ runId, vaultId, flow }),
  } as unknown as ChatAppContext;

  try {
    await openCitationTarget({ kind: "run", run_id: "run_chat_ingest", vault_id: "work" }, context);
    expect(opened).toEqual([{ runId: "run_chat_ingest", vaultId: "work", flow: "ingest" }]);
    await expect(openCitationTarget({ kind: "report", path: "reports/ingest.md" }, context))
      .rejects.toThrow("missing its knowledge-base identity");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("management console renders core navigation", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/KnoArbor Console/);
  await expect(page.getByRole("button", { name: /^(Chat|对话)$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^(Flows|流程)$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^(Knowledge|知识)$/ })).toBeVisible();

  await page.getByRole("button", { name: /^(Workspace Settings|工作区设置)$/ }).click();
  await expect(page.getByRole("dialog").getByText(/Workspace Settings|工作区设置/).first()).toBeVisible();
  await expect(page.getByRole("tab", { name: /^(Vault|知识库)$/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: /^(New knowledge base|新增知识库)$/ })).toBeVisible();
  await page.getByRole("tab", { name: /^(Inputs|输入来源)$/ }).click();
  await expect(page.getByRole("heading", { name: /^(Chat record inputs|聊天记录输入)$/ })).toBeVisible();
  await page.getByRole("tab", { name: /^(General|通用)$/ }).click();
  await expect(page.getByRole("heading", { name: /^(Appearance|外观)$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^(Updates|更新)$/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByRole("button", { name: /^(Knowledge|知识)$/ }).click();
  await page.getByRole("button", { name: /^(Graph|知识图谱)$/ }).click();
  await expect(page.locator("main").getByText(/Graph|知识图谱/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Page relationship graph|页面关系图/ })).toBeVisible();
  await expect(page.getByText(/No pages to display|没有可展示的页面/)).toBeVisible();
});

test("narrow desktop chat keeps the composer and send action inside the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 1080, height: 720 });
  await page.goto("/");
  const composer = page.locator(".chat-composer");
  const send = composer.getByRole("button", { name: /^(Send|发送)$/ });
  await expect(composer).toBeVisible();
  await expect(send).toBeVisible();
  const composerBox = await composer.boundingBox();
  const sendBox = await send.boundingBox();
  expect(composerBox).not.toBeNull();
  expect(sendBox).not.toBeNull();
  expect((composerBox?.y || 0) + (composerBox?.height || 0)).toBeLessThanOrEqual(720);
  expect((sendBox?.y || 0) + (sendBox?.height || 0)).toBeLessThanOrEqual(720);
});

test("chat selectors keep stable slots and truncate long labels", async ({ page }) => {
  await page.setViewportSize({ width: 1080, height: 720 });
  await page.goto("/");
  const vaultSelect = page.locator(".chat-vault-toolbar select");
  await expect(vaultSelect).toBeVisible();
  await page.evaluate(() => {
    const footer = document.querySelector(".chat-input-footer");
    if (!footer || footer.querySelector(".chat-model-toolbar")) return;
    const toolbar = document.createElement("div");
    toolbar.className = "chat-model-toolbar";
    const select = document.createElement("select");
    select.setAttribute("aria-label", "Model");
    select.append(new Option("aliyun", "aliyun"));
    toolbar.append(select);
    footer.insertBefore(toolbar, footer.lastElementChild);
  });
  const modelSelect = page.locator(".chat-model-toolbar select");
  await expect(modelSelect).toBeVisible();

  const initialWidths = await Promise.all([vaultSelect, modelSelect].map(async (select) => (await select.boundingBox())?.width));
  expect(initialWidths).toEqual([104, 104]);
  await Promise.all([vaultSelect, modelSelect].map((select, index) => select.evaluate((element, labelIndex) => {
    const option = document.createElement("option");
    option.value = `long-${labelIndex}`;
    option.textContent = labelIndex === 0
      ? "这是一个非常长但必须保持完整值的知识库名称"
      : "provider-with-a-very-long-model-configuration-name";
    element.append(option);
    element.value = option.value;
  }, index)));
  const finalWidths = await Promise.all([vaultSelect, modelSelect].map(async (select) => (await select.boundingBox())?.width));

  expect(initialWidths).toEqual(finalWidths);
  for (const select of [vaultSelect, modelSelect]) {
    await expect(select).toHaveCSS("text-overflow", "ellipsis");
    await expect(select).toHaveCSS("white-space", "nowrap");
    await expect(select).toHaveCSS("text-align", "left");
  }
});

test("settings start from custom model presets and persist a newly selected knowledge base", async ({ page }) => {
  let persistedForm = emptySettingsForm();
  let savedForm: Record<string, unknown> | null = null;

  await page.addInitScript(() => {
    (window as unknown as { __legacyDirectoryDeleteCalled: boolean }).__legacyDirectoryDeleteCalled = false;
    window.knoarborDesktop = {
      getEnvironment: async () => ({
        isDesktopApp: true,
        platform: "darwin",
        versions: { chrome: "test", electron: "test", node: "test" },
      }),
      onCommand: () => () => undefined,
      selectDirectory: async () => ({ canceled: false, path: "/tmp/knoarbor-test/知识库测试" }),
      deleteDirectory: async () => {
        (window as unknown as { __legacyDirectoryDeleteCalled: boolean }).__legacyDirectoryDeleteCalled = true;
        return { deleted: true };
      },
    } as unknown as typeof window.knoarborDesktop;
  });
  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const { pathname } = new URL(request.url());
    if (pathname === "/config/form") {
      if (request.method() === "PUT") {
        const { config_path: _configPath, ...nextForm } = request.postDataJSON() as Record<string, unknown>;
        persistedForm = nextForm;
        savedForm = nextForm;
        await route.fulfill({
          json: {
            config_path: "/tmp/knoarbor-test/config.yaml",
            summary: {
              project_name: nextForm.project_name,
              vault_id: nextForm.vault_id,
              vault_name: nextForm.project_name,
              vault_path: nextForm.vault_path,
            },
          },
        });
        return;
      }
      await route.fulfill({ json: persistedForm });
      return;
    }
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": {
        config_path: "/tmp/knoarbor-test/config.yaml",
        exists: true,
        content: "",
        summary: {
          project_name: "Personal",
          vault_id: "personal",
          vault_name: "Personal",
          vault_path: "/tmp/knoarbor-test/personal",
        },
      },
      "/config/diagnostics": { providers: [], paths: [], connectors: [], processors: [] },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: null, providers: [] },
      "/vaults": {
        schema_version: "vaults.v1",
        config_path: "/tmp/knoarbor-test/config.yaml",
        default_vault_id: "personal",
        vaults: [{ id: "personal", name: "Personal", path: "/tmp/knoarbor-test/personal", exists: true }],
      },
      "/sources": { schema_version: "source_catalog.v1", connectors: [] },
      "/chat/sessions": { schema_version: "chat_session_list.v1", sessions: [] },
      "/runs": { runs: [] },
      "/reports": { vault_path: "/tmp/knoarbor-test/personal", vault_id: "personal", reports: [] },
      "/vaults/status": {},
    };
    await route.fulfill({ json: responses[pathname] || {} });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /^(Workspace Settings|工作区设置)$/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: /^(New knowledge base|新增知识库)$/ }).click();

  await expect.poll(() => savedForm).not.toBeNull();
  expect(savedForm).toMatchObject({
    project_name: "知识库测试",
    vault_id: "vault",
    vault_path: "/tmp/knoarbor-test/知识库测试",
    vaults: [
      { id: "personal", active: false },
      { id: "vault", name: "知识库测试", path: "/tmp/knoarbor-test/知识库测试", active: true },
    ],
  });
  await expect(dialog.locator('input[value="/tmp/knoarbor-test/知识库测试"]')).toBeVisible();

  page.once("dialog", async (confirmation) => {
    expect(confirmation.message()).toMatch(/remain unchanged|不会被删除/);
    await confirmation.accept();
  });
  await dialog.getByRole("button", { name: /^(Remove vault|移除知识库)$/ }).last().click();
  await expect.poll(() => (savedForm?.vaults as unknown[] | undefined)?.length).toBe(1);
  expect(await page.evaluate(() => (window as unknown as { __legacyDirectoryDeleteCalled: boolean }).__legacyDirectoryDeleteCalled)).toBe(false);

  await dialog.getByRole("tab", { name: /^(Models|模型)$/ }).click();
  const textPreset = dialog.getByRole("button", { name: /^(Provider type|供应商类型)$/ });
  const imagePreset = dialog.getByRole("button", { name: /^(Image model preset|生图模型预设)$/ });
  await expect(textPreset).toHaveText(/^(Custom|自定义)$/);
  await expect(imagePreset).toHaveText(/^(Custom|自定义)$/);
  await expect(textPreset.locator("svg.custom-select-chevron")).toBeVisible();
  await expect(imagePreset.locator("svg.custom-select-chevron")).toBeVisible();
});

test("model settings preserve continued editing while field saves complete", async ({ page }) => {
  let persistedForm = emptySettingsForm();
  const savedForms: Record<string, unknown>[] = [];
  let completedSaves = 0;
  let baseUrlSaveCompleted = false;

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const { pathname } = new URL(request.url());
    if (pathname === "/config/form") {
      if (request.method() === "PUT") {
        const { config_path: _configPath, ...nextForm } = request.postDataJSON() as Record<string, unknown>;
        savedForms.push(nextForm);
        const provider = (nextForm.providers as Array<Record<string, unknown>> | undefined)?.[0];
        const isBaseUrlSave = provider?.base_url === "https://models.example.test/v1" && provider.model === "";
        if (isBaseUrlSave) {
          await new Promise((resolve) => setTimeout(resolve, 300));
        }
        persistedForm = nextForm;
        await route.fulfill({ json: { config_path: "/tmp/knoarbor-test/config.yaml", summary: {} } });
        completedSaves += 1;
        if (isBaseUrlSave) baseUrlSaveCompleted = true;
        return;
      }
      await route.fulfill({ json: persistedForm });
      return;
    }
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": { config_path: "/tmp/knoarbor-test/config.yaml", exists: true, content: "", summary: {} },
      "/config/diagnostics": { providers: [], paths: [], connectors: [], processors: [] },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: null, providers: [] },
      "/vaults": { schema_version: "vaults.v1", default_vault_id: "personal", vaults: [] },
      "/sources": { schema_version: "source_catalog.v1", connectors: [] },
      "/chat/sessions": { schema_version: "chat_session_list.v1", sessions: [] },
      "/runs": { runs: [] },
      "/reports": { vault_path: "", vault_id: "personal", reports: [] },
      "/vaults/status": {},
    };
    await route.fulfill({ json: responses[pathname] || {} });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /^(Workspace Settings|工作区设置)$/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("tab", { name: /^(Models|模型)$/ }).click();
  await dialog.getByRole("button", { name: /^(Add model|新增模型)$/ }).click();
  await expect.poll(() => completedSaves).toBeGreaterThanOrEqual(1);

  const baseUrl = dialog.getByLabel("Base URL").first();
  const model = dialog.getByLabel(/^(Model|模型)$/).first();
  await baseUrl.fill("https://models.example.test/v1");
  await model.fill("model-written-while-base-url-saves");

  await expect.poll(() => baseUrlSaveCompleted).toBe(true);
  await expect(model).toHaveValue("model-written-while-base-url-saves");
  expect(savedForms.find((savedForm) => (
    savedForm.providers as Array<Record<string, unknown>> | undefined
  )?.[0]?.base_url === "https://models.example.test/v1")).toMatchObject({
    providers: [{ base_url: "https://models.example.test/v1", model: "" }],
  });

  await model.press("Tab");
  await expect.poll(() => savedForms.find((savedForm) => (
    savedForm.providers as Array<Record<string, unknown>> | undefined
  )?.[0]?.model === "model-written-while-base-url-saves")).toBeTruthy();
  expect(savedForms.at(-1)).toMatchObject({
    providers: [{ base_url: "https://models.example.test/v1", model: "model-written-while-base-url-saves" }],
  });
});

test("completed ingest invalidates a previously cached knowledge page list", async ({ page }) => {
  let runStarted = false;
  let runCompleted = false;
  let activeRunPolls = 0;
  let pageListRequests = 0;
  let pageRefreshStarted = false;
  const runRecord = (status: "running" | "completed") => ({
    run_id: "run_generated_page",
    vault_id: "personal",
    vault_path: "/tmp/knoarbor-test/personal",
    flow: "ingest",
    status,
    stage: status === "completed" ? "completed" : "materialization",
    current_item: "fixture.md",
    message: status === "completed" ? "Ingest run completed." : "Materializing generated pages.",
    started_at: "2026-07-23T00:00:00Z",
    updated_at: status === "completed" ? "2026-07-23T00:00:02Z" : "2026-07-23T00:00:01Z",
    last_heartbeat_at: "2026-07-23T00:00:01Z",
    elapsed_seconds: status === "completed" ? 2 : 1,
    progress: { completed: status === "completed" ? 1 : 0, total: 1 },
    metrics: {},
    result_summary: status === "completed" ? { written_pages: ["generated-page.md"] } : {},
    metadata: {},
    cancel_requested: false,
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const url = new URL(request.url());
    if (url.pathname === "/wiki/pages") {
      pageListRequests += 1;
      if (runCompleted) {
        pageRefreshStarted = true;
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      await route.fulfill({ json: {
        vault_id: "personal",
        vault_path: "/tmp/knoarbor-test/personal",
        pages: runCompleted ? [{
          path: "generated-page.md",
          canonical_path: "generated-page.md",
          directory: "pages",
          title: "Generated page",
          role: "knowledge_page",
          updated: "2026-07-23T00:00:00Z",
          entities: [],
          summary: "Generated after ingest.",
          headings: [],
        }] : [],
      } });
      return;
    }
    if (url.pathname === "/runs" && url.searchParams.get("active_only") === "true") {
      if (!runStarted) {
        await route.fulfill({ json: { runs: [] } });
        return;
      }
      activeRunPolls += 1;
      if (activeRunPolls === 1) {
        await route.fulfill({ json: { runs: [runRecord("running")] } });
        return;
      }
      runCompleted = true;
      await route.fulfill({ json: { runs: [] } });
      return;
    }
    if (url.pathname === "/runs" && url.searchParams.get("active_only") !== "true") {
      await route.fulfill({ json: { runs: runCompleted ? [runRecord("completed")] : [] } });
      return;
    }
    if (url.pathname === "/runs/events") {
      await route.fulfill({ json: { events: [], next_cursor: 0 } });
      return;
    }
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": {
        config_path: "/tmp/knoarbor-test/config.yaml",
        exists: true,
        content: "",
        summary: {
          project_name: "KnoArbor Test",
          vault_id: "personal",
          vault_name: "Personal",
          vault_path: "/tmp/knoarbor-test/personal",
        },
      },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: null, providers: [] },
      "/vaults": {
        schema_version: "vaults.v1",
        config_path: "/tmp/knoarbor-test/config.yaml",
        default_vault_id: "personal",
        vaults: [{ id: "personal", name: "Personal", path: "/tmp/knoarbor-test/personal", exists: true }],
      },
      "/vaults/status": { pages: 0, raw_sources: 0, issues: 0 },
      "/wiki/pages/content": {
        path: "generated-page.md",
        canonical_path: "generated-page.md",
        vault_id: "personal",
        vault_path: "/tmp/knoarbor-test/personal",
        content: "# Generated page\n\nGenerated after ingest with $E=mc^2$.",
        metadata: {},
        summary: {
          path: "generated-page.md",
          canonical_path: "generated-page.md",
          directory: "pages",
          title: "Generated page",
          role: "knowledge_page",
          entities: [],
          summary: "Generated after ingest.",
          headings: ["Generated page"],
        },
        outgoing_pages: [],
        incoming_pages: [],
        default_view: "raw",
        raw_content: "# Generated source\n\nInline $E=mc^2$.\n\n$$\na^2+b^2=c^2\n$$",
        editable_projection: null,
        editable_raw: null,
      },
      "/runs": { runs: [] },
      "/reports": {
        vault_id: "personal",
        vault_path: "/tmp/knoarbor-test/personal",
        reports: [{
          path: "maintenance/reports/ingest-generated-page.md",
          vault_id: "personal",
          vault_path: "/tmp/knoarbor-test/personal",
          title: "Ingest generated page",
          kind: "ingest",
          updated: "2026-07-23T00:00:02Z",
          size: 80,
          preview: "Generated pages: generated-page.md",
        }],
      },
      "/reports/content": {
        path: "maintenance/reports/ingest-generated-page.md",
        vault_id: "personal",
        vault_path: "/tmp/knoarbor-test/personal",
        content: "# Ingest report\n\nGenerated pages:\n- generated-page.md",
        summary: {
          path: "maintenance/reports/ingest-generated-page.md",
          vault_id: "personal",
          vault_path: "/tmp/knoarbor-test/personal",
          title: "Ingest generated page",
          kind: "ingest",
          updated: "2026-07-23T00:00:02Z",
          size: 80,
          preview: "Generated pages: generated-page.md",
        },
      },
      "/sources": { schema_version: "source_catalog.v1", connectors: [] },
      "/chat/sessions": { schema_version: "chat_session_list.v1", sessions: [] },
    };
    await route.fulfill({ json: responses[url.pathname] || {} });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /^(Knowledge|知识)$/ }).click();
  await expect(page.getByText(/No pages yet|暂无页面/)).toBeVisible();
  expect(pageListRequests).toBe(1);

  await page.getByRole("button", { name: /^(Flows|流程)$/ }).click();
  runStarted = true;
  await expect(page.getByText("Materializing generated pages.", { exact: true }).first()).toBeVisible({ timeout: 10_000 });
  await expect.poll(() => runCompleted, { timeout: 10_000 }).toBe(true);
  await expect(page.getByText(/No active runs|当前没有正在运行的任务/)).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: /^(View in Knowledge Base|知识库查看)$/ }).click();

  await expect.poll(() => pageRefreshStarted).toBe(true);
  const generatedPage = page.getByRole("button", { name: /Generated page/ });
  await expect(generatedPage).toBeVisible();
  await generatedPage.click();
  await expect(page.locator(".markdown-rendered .katex")).toHaveCount(2);
  await expect(page.locator(".markdown-rendered .katex-display")).toHaveCount(1);
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(pageListRequests).toBeGreaterThanOrEqual(2);
});

test("selecting a discovered model clears the prior empty-model assessment", async ({ page }) => {
  let configWrites = 0;
  let persistedForm = {
    ...emptySettingsForm(),
    default_provider: "qwen",
    providers: [{
      name: "qwen",
      adapter: "openai_compatible",
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      api_key: "test-key",
      model: "",
      json_mode: true,
      tls_ca_file: "",
      context_window: null,
      max_output_tokens: null,
      extra_body: {},
    }],
  };

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const { pathname } = new URL(request.url());
    if (pathname === "/config/form") {
      if (request.method() === "PUT") {
        configWrites += 1;
        const { config_path: _configPath, ...nextForm } = request.postDataJSON() as Record<string, unknown>;
        persistedForm = nextForm as typeof persistedForm;
        await route.fulfill({ json: { config_path: "/tmp/knoarbor-test/config.yaml", summary: {} } });
        return;
      }
      await route.fulfill({ json: persistedForm });
      return;
    }
    if (pathname === "/models/discover") {
      await route.fulfill({
        json: {
          schema_version: "model_discovery.v1",
          provider: "qwen",
          model: "",
          status: "ok",
          available: true,
          message: "ok",
          model_ids: ["qwen3.7-max", "qwen-plus"],
          model_count: 2,
          configured_model_found: false,
          context_window_source: "unknown",
          suggested_config: {},
          details: {},
        },
      });
      return;
    }
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": { config_path: "/tmp/knoarbor-test/config.yaml", exists: true, content: "", summary: {} },
      "/config/diagnostics": { providers: [], paths: [], connectors: [], processors: [] },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: "qwen", providers: [] },
      "/vaults": { schema_version: "vaults.v1", default_vault_id: "personal", vaults: [] },
      "/sources": { schema_version: "source_catalog.v1", connectors: [] },
      "/chat/sessions": { schema_version: "chat_session_list.v1", sessions: [] },
      "/runs": { runs: [] },
      "/reports": { vault_path: "", vault_id: "personal", reports: [] },
      "/vaults/status": {},
    };
    await route.fulfill({ json: responses[pathname] || {} });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /^(Workspace Settings|工作区设置)$/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("tab", { name: /^(Models|模型)$/ }).click();
  configWrites = 0;
  await dialog.getByRole("button", { name: /^(Discover models|检查模型)$/ }).click();
  await expect(dialog.getByText(/qwen3\.7-max/)).toBeVisible();
  expect(configWrites).toBe(0);
  await dialog.getByRole("button", { name: /^(Use model|使用模型)$/ }).first().click();

  await expect(dialog.getByRole("button", { name: /^(Selected|已选择)$/ })).toBeVisible();
  await expect(dialog.getByText(/configured model was not found|当前填写的模型未在该供应商中发现/)).toHaveCount(0);
  await expect(dialog.getByText(/^(Model available|模型可用)$/).first()).toBeVisible();
});

test("provider checks reuse persisted settings and image checks use explicit generation", async ({ page }) => {
  const settingsForm = {
    ...emptySettingsForm(),
    image_default_provider: "local-image",
    image_providers: [{
      name: "local-image",
      adapter: "openai_chat_image",
      base_url: "https://text2image.local/v1",
      endpoint_path: "/chat/completions",
      api_key: "test-key",
      model: "SenseNova-U1-8B",
      tls_ca_file: "",
      resolution: "",
      num_inference_steps: 20,
      guidance: 4,
      extra_body: {},
    }],
  };
  const calls: string[] = [];
  let configWrites = 0;
  let configSaveCompleted = false;
  let imageProbeStartedAfterSave = false;

  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const { pathname } = new URL(request.url());
    calls.push(`${request.method()} ${pathname}`);
    if (pathname === "/config/form") {
      if (request.method() === "PUT") {
        configWrites += 1;
        await new Promise((resolve) => setTimeout(resolve, 100));
        configSaveCompleted = true;
        await route.fulfill({ json: { config_path: "/tmp/knoarbor-test/config.yaml", summary: {} } });
        return;
      }
      await route.fulfill({ json: settingsForm });
      return;
    }
    if (pathname === "/models/image-probe") {
      imageProbeStartedAfterSave = configSaveCompleted;
      await route.fulfill({
        json: {
          schema_version: "image_provider_probe.v1",
          provider: "local-image",
          model: "SenseNova-U1-8B",
          adapter: "openai_chat_image",
          status: "ok",
          available: true,
          message: "Image generation completed successfully.",
          elapsed_ms: 842,
          image_count: 1,
          mime_types: ["image/png"],
          error_code: null,
          retryable: false,
        },
      });
      return;
    }
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": { config_path: "/tmp/knoarbor-test/config.yaml", exists: true, content: "", summary: {} },
      "/config/diagnostics": { providers: [], paths: [], connectors: [], processors: [] },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: "", providers: [] },
      "/vaults": { schema_version: "vaults.v1", default_vault_id: "personal", vaults: [] },
      "/sources": { schema_version: "source_catalog.v1", connectors: [] },
      "/chat/sessions": { schema_version: "chat_session_list.v1", sessions: [] },
      "/runs": { runs: [] },
      "/reports": { vault_path: "", vault_id: "personal", reports: [] },
      "/vaults/status": {},
    };
    await route.fulfill({ json: responses[pathname] || {} });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /^(Workspace Settings|工作区设置)$/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("tab", { name: /^(Models|模型)$/ }).click();
  calls.length = 0;
  configWrites = 0;
  configSaveCompleted = false;
  await dialog.getByLabel(/^(Model|模型)$/).last().fill("SenseNova-U1-8B-updated");
  await dialog.getByRole("button", { name: /^(Test image generation|测试生图)$/ }).click();

  await expect(dialog.getByText(/^(Image generation available|生图可用)$/)).toBeVisible();
  await expect(dialog.getByText("842 ms")).toBeVisible();
  expect(configWrites).toBe(1);
  expect(imageProbeStartedAfterSave).toBe(true);
  expect(calls).toContain("PUT /config/form");
  expect(calls).toContain("POST /models/image-probe");
  expect(calls.some((call) => call.includes("/config/diagnostics"))).toBe(false);
  expect(calls.some((call) => call.includes("/sources"))).toBe(false);
});

function emptySettingsForm(): Record<string, unknown> {
  return {
    project_name: "Personal",
    vault_path: "/tmp/knoarbor-test/personal",
    vault_id: "personal",
    vaults: [{ id: "personal", name: "Personal", path: "/tmp/knoarbor-test/personal", active: true }],
    server_host: "127.0.0.1",
    server_port: 8000,
    default_provider: "",
    default_max_tokens: 12000,
    request_timeout_seconds: 300,
    providers: [],
    image_default_provider: "",
    image_request_timeout_seconds: 120,
    image_providers: [],
    enabled_connectors: [],
    detected_chat_source_dirs: {},
    codex_enabled: false,
    codex_sessions_dir: "",
    codex_raw_output_dir: "",
    hermes_enabled: false,
    hermes_sessions_dir: "",
    hermes_raw_output_dir: "",
    openclaw_enabled: false,
    openclaw_sessions_dir: "",
    openclaw_raw_output_dir: "",
    claude_code_enabled: false,
    claude_code_sessions_dir: "",
    claude_code_raw_output_dir: "",
    generic_chat_enabled: false,
    generic_chat_roots: [],
    generic_chat_raw_output_dir: "",
    markdown_enabled: false,
    markdown_roots: [],
    markdown_raw_output_dir: "",
    mineru_enabled: true,
    mineru_endpoint: "http://127.0.0.1:18000/file_parse",
    mineru_input_dir: "",
    mineru_output_dir: "",
    mineru_parse_method: "auto",
    mineru_backend: "pipeline",
    mineru_timeout_seconds: 600,
    mineru_patterns: ["*.pdf", "*.docx", "*.pptx"],
    mineru_recursive: true,
    mineru_return_md: true,
    mineru_return_middle_json: false,
    mineru_return_model_output: false,
    mineru_return_content_list: false,
    mineru_return_images: true,
    mineru_response_format_zip: false,
    mineru_lang_list: "ch",
    mineru_formula_enable: true,
    mineru_table_enable: true,
    mineru_server_url: "",
    mineru_start_page_id: 0,
    mineru_end_page_id: 99999,
    mineru_extra_fields_json: "{}",
  };
}

test("custom input submits the edited excerpt through the shared ingest contract", async ({ page }) => {
  let ingestBody: Record<string, unknown> | null = null;
  let ingestAttempts = 0;
  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const { pathname } = new URL(request.url());
    if (pathname === "/ingest" && request.method() === "POST") {
      ingestAttempts += 1;
      ingestBody = request.postDataJSON() as Record<string, unknown>;
      if (ingestAttempts === 1) {
        await route.fulfill({ status: 400, json: { detail: "Text model configuration is missing." } });
        return;
      }
      await route.fulfill({ json: { run_id: "run_manual_excerpt", status: "queued" } });
      return;
    }
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": {
        config_path: "/tmp/knoarbor-test/config.yaml",
        exists: true,
        content: "",
        summary: {
          project_name: "KnoArbor Test",
          vault_id: "personal",
          vault_name: "Personal",
          vault_path: "/tmp/knoarbor-test/personal",
        },
      },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: null, providers: [] },
      "/vaults": {
        schema_version: "vaults.v1",
        config_path: "/tmp/knoarbor-test/config.yaml",
        default_vault_id: "personal",
        vaults: [{ id: "personal", name: "Personal", path: "/tmp/knoarbor-test/personal", exists: true }],
      },
      "/sources": { schema_version: "source_catalog.v1", connectors: [{ name: "codex", enabled: true }] },
      "/chat/sessions": { schema_version: "chat_session_list.v1", sessions: [] },
      "/runs": { runs: [] },
      "/reports": { vault_path: "/tmp/knoarbor-test/personal", vault_id: "personal", reports: [] },
      "/vaults/status": {},
    };
    await route.fulfill({ json: responses[pathname] || {} });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /^(Flows|流程)$/ }).click();
  await expect(page.getByRole("option", { name: "Codex" })).toHaveCount(1);
  const openCustomInput = page.getByRole("button", { name: /^(Enter content|输入内容)$/ });
  await expect(openCustomInput).toBeVisible();
  await openCustomInput.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const submit = dialog.getByRole("button", { name: /^(Import Materials|导入资料)$/ });
  await expect(submit).toBeDisabled();
  await dialog.getByLabel(/^(Title|标题)$/).fill("Edited manual note");
  await dialog.getByLabel(/^(Content|正文)$/).fill("The final edited content is the source of truth.");
  await submit.click();

  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("alert")).toContainText(/model configuration|模型配置/i);
  await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
  await submit.click();

  await expect.poll(() => ingestAttempts).toBe(2);
  expect(ingestBody).toMatchObject({
    kind: "excerpt",
    vault_id: "personal",
    excerpt_title: "Edited manual note",
    excerpt_text: "The final edited content is the source of truth.",
    excerpt_context: {
      source_app: "knoarbor",
      input_method: "manual_editor",
    },
  });
  await expect(dialog).toBeHidden();
});

test("session deletion uses the shared in-app confirmation dialog", async ({ page }) => {
  let nativeDialogOpened = false;
  page.on("dialog", async (dialog) => {
    nativeDialogOpened = true;
    await dialog.dismiss();
  });
  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const url = new URL(request.url());
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": {
        config_path: "/tmp/knoarbor-test/config.yaml",
        exists: true,
        content: "",
        summary: {
          project_name: "KnoArbor Test",
          vault_id: "personal",
          vault_name: "Personal",
          vault_path: "/tmp/knoarbor-test/personal",
        },
      },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: null, providers: [] },
      "/vaults": {
        schema_version: "vaults.v1",
        config_path: "/tmp/knoarbor-test/config.yaml",
        default_vault_id: "personal",
        vaults: [{ id: "personal", name: "Personal", path: "/tmp/knoarbor-test/personal", exists: true }],
      },
      "/sources": { schema_version: "source_catalog.v1", connectors: [] },
      "/runs": { runs: [] },
      "/reports": { vault_path: "/tmp/knoarbor-test/personal", vault_id: "personal", reports: [] },
      "/vaults/status": {},
    };
    if (url.pathname === "/chat/sessions") {
      const sessions = url.searchParams.get("vault_id") === "personal"
        ? [{
            session_id: "session-delete-test",
            title: "Aurora notes",
            created_at: "2026-07-16T00:00:00Z",
            updated_at: "2026-07-16T01:00:00Z",
            vault_id: "personal",
            vault_name: "Personal",
            vault_path: "/tmp/knoarbor-test/personal",
            message_count: 2,
            last_message: "Aurora notes",
          }]
        : [];
      await route.fulfill({ json: { schema_version: "chat_session_list.v1", sessions } });
      return;
    }
    if (url.pathname === "/chat/sessions/session-delete-test") {
      await route.fulfill({ status: 404, json: { detail: "Session not found" } });
      return;
    }
    await route.fulfill({ json: responses[url.pathname] || {} });
  });

  await page.goto("/");
  const sessionButton = page.getByRole("button", { name: "Aurora notes" });
  await expect(sessionButton).toBeVisible();
  await page.getByRole("button", { name: /^(Knowledge|知识)$/ }).click();
  await expect(sessionButton).toBeVisible();
  await page.getByRole("button", { name: /^(Flows|流程)$/ }).click();
  await expect(sessionButton).toBeVisible();
  await page.getByRole("button", { name: /^(Chat|对话)$/ }).click();
  await expect(sessionButton).toBeVisible();
  await page.getByRole("button", { name: "Session menu" }).click();
  await page.getByRole("button", { name: /^(Delete|删除)$/ }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: /^(Delete session|删除会话)$/ })).toBeVisible();
  await expect(dialog.getByText("Aurora notes")).toBeVisible();
  expect(nativeDialogOpened).toBe(false);
  await dialog.getByRole("button", { name: /^(Cancel|取消)$/ }).click();
  await sessionButton.click();
  await expect(page.getByRole("alert").getByText(/requested session does not exist|该会话不存在/)).toBeVisible();
});

test("conversation sidebar preserves available history and reports failed vault groups", async ({ page }) => {
  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const url = new URL(request.url());
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": {
        config_path: "/tmp/knoarbor-test/config.yaml",
        exists: true,
        content: "",
        summary: {
          project_name: "KnoArbor Test",
          vault_id: "personal",
          vault_name: "Personal",
          vault_path: "/tmp/knoarbor-test/personal",
        },
      },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: null, providers: [] },
      "/vaults": {
        schema_version: "vaults.v1",
        config_path: "/tmp/knoarbor-test/config.yaml",
        default_vault_id: "personal",
        vaults: [
          { id: "personal", name: "Personal", path: "/tmp/knoarbor-test/personal", exists: true },
          { id: "work", name: "Work", path: "/tmp/knoarbor-test/work", exists: true },
        ],
      },
      "/sources": { schema_version: "source_catalog.v1", connectors: [] },
      "/runs": { runs: [] },
      "/reports": { vault_path: "/tmp/knoarbor-test/personal", vault_id: "personal", reports: [] },
      "/vaults/status": {},
    };
    if (url.pathname === "/chat/sessions") {
      const vaultId = url.searchParams.get("vault_id");
      if (vaultId === "work") {
        await route.fulfill({ status: 503, json: { detail: "Service unavailable" } });
        return;
      }
      const sessions = vaultId === "personal"
        ? [{
            session_id: "session-personal-history",
            session_revision: 1,
            title: "Retained personal history",
            created_at: "2026-07-16T00:00:00Z",
            updated_at: "2026-07-16T01:00:00Z",
            vault_id: "personal",
            vault_name: "Personal",
            vault_path: "/tmp/knoarbor-test/personal",
            message_count: 2,
            last_message: "Retained personal history",
          }]
        : [];
      await route.fulfill({
        json: {
          schema_version: "chat_session_list.v1",
          sessions,
          total_count: sessions.length,
          offset: 0,
          limit: 200,
          has_more: false,
        },
      });
      return;
    }
    await route.fulfill({ json: responses[url.pathname] || {} });
  });

  await page.goto("/");
  await expect(page.getByRole("button", { name: "Retained personal history" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(
    /1 knowledge base history group|1 个知识库的历史会话/,
  );
  await expect(page.getByRole("button", { name: /^(Retry|重试)$/ })).toBeVisible();
});

test("secondary navigation vault switch keeps Chat scope and retained workspace state separate", async ({ page }) => {
  const requestedUrls: string[] = [];
  await page.route("**/*", async (route) => {
    const request = route.request();
    if (request.resourceType() !== "fetch") {
      await route.continue();
      return;
    }
    const url = new URL(request.url());
    requestedUrls.push(url.toString());
    const vaultPath = url.searchParams.get("vault_path") || "/tmp/knoarbor-test/personal";
    const vaultId = url.searchParams.get("vault_id") || (vaultPath.endsWith("/work") ? "work" : "personal");
    const responses: Record<string, unknown> = {
      "/health": { status: "ok" },
      "/config": {
        config_path: "/tmp/knoarbor-test/config.yaml",
        exists: true,
        content: "",
        summary: {
          project_name: "KnoArbor Test",
          vault_id: "personal",
          vault_name: "Personal",
          vault_path: "/tmp/knoarbor-test/personal",
        },
      },
      "/models/providers": { schema_version: "model_providers.v1", default_provider: null, providers: [] },
      "/vaults": {
        schema_version: "vaults.v1",
        config_path: "/tmp/knoarbor-test/config.yaml",
        default_vault_id: "personal",
        vaults: [
          { id: "personal", name: "Personal", path: "/tmp/knoarbor-test/personal", exists: true },
          { id: "work", name: "Work", path: "/tmp/knoarbor-test/work", exists: true },
        ],
      },
      "/chat/sessions": { schema_version: "chat_session_list.v1", sessions: [] },
      "/vaults/status": { pages: 0, raw_sources: 0, issues: 0 },
      "/wiki/pages": { vault_id: vaultId, vault_path: vaultPath, pages: [] },
      "/wiki/graph": {
        graph_kind: "page",
        nodes: vaultId === "personal" ? [{
          id: "personal-page.md",
          title: "Personal page",
          type: "page",
          summary: "Personal graph node",
          entities: [],
        }] : [],
        edges: [],
        stats: {
          page_count: vaultId === "personal" ? 1 : 0,
          edge_count: 0,
          orphan_count: vaultId === "personal" ? 1 : 0,
          unresolved_link_count: 0,
          directory_counts: {},
          role_counts: {},
          entity_counts: {},
        },
      },
      "/wiki/pages/content": {
        path: "personal-page.md",
        content: "# Personal page",
        metadata: {},
        summary: {
          path: "personal-page.md",
          directory: "",
          title: "Personal page",
          entities: [],
          summary: "Personal graph node",
          headings: [],
        },
        outgoing_pages: [],
        incoming_pages: [],
      },
      "/runs": { runs: [] },
      "/reports": { vault_id: vaultId, vault_path: vaultPath, reports: [] },
      "/tokens": { record_count: 0 },
      "/sources": { schema_version: "source_catalog.v1", connectors: [] },
    };
    await route.fulfill({ json: responses[url.pathname] || {} });
  });

  await page.goto("/");
  const composer = page.locator(".chat-composer textarea");
  const chatScope = page.locator(".chat-vault-toolbar select");
  await chatScope.selectOption("all");
  await expect(chatScope).toHaveValue("all");
  await composer.fill("retain this draft");

  await page.getByRole("button", { name: /^(Flows|流程)$/ }).click();
  const pageVaultSwitch = page.locator(".secondary-nav-row .page-vault-switcher");
  await expect(pageVaultSwitch).toHaveValue("personal");
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), pageVaultStorageKey("ingest"))).toBe("personal");
  await page.getByRole("button", { name: /^(Tokens|令牌|Token 分析)$/ }).click();
  await pageVaultSwitch.selectOption("work");
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), pageVaultStorageKey("ingest"))).toBe("personal");
  await page.getByRole("button", { name: /^(Ingest|导入资料)$/ }).click();
  await expect(pageVaultSwitch).toHaveValue("personal");

  await page.getByRole("button", { name: /^(Knowledge|知识)$/ }).click();
  const wikiVaultSwitch = pageVaultSwitch;
  await expect(wikiVaultSwitch).toHaveValue("personal");
  await wikiVaultSwitch.selectOption("work");
  await expect.poll(() => requestedUrls.some((value) => value.includes("/wiki/pages") && value.includes("vault_id=work"))).toBe(true);

  await page.getByRole("button", { name: /^(Graph|知识图谱)$/ }).click();
  const graphVaultSwitch = pageVaultSwitch;
  await expect(graphVaultSwitch).toHaveValue("work");
  await expect(page.getByText(/No pages to display|没有可展示的页面/)).toBeVisible();
  await graphVaultSwitch.selectOption("personal");
  await expect(page.locator(".graph-canvas-engine canvas").first()).toBeVisible();
  await graphVaultSwitch.selectOption("work");
  await expect(page.getByText(/No pages to display|没有可展示的页面/)).toBeVisible();
  await graphVaultSwitch.selectOption("personal");
  await expect(page.locator(".graph-canvas-engine canvas").first()).toBeVisible();
  const graphSearch = page.locator(".graph-toolbar-search input");
  await graphSearch.fill("missing node");
  await expect(page.getByText(/No pages to display|没有可展示的页面/)).toBeVisible();
  await graphSearch.fill("");
  await expect(page.locator(".graph-canvas-engine canvas").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Page load failed|页面加载失败/ })).toHaveCount(0);

  await page.getByRole("button", { name: /^(Flows|流程)$/ }).click();
  await expect(pageVaultSwitch).toHaveValue("personal");
  await expect(page.locator(".secondary-nav").getByRole("button", { name: /^(Sources|资料来源)$/ })).toHaveCount(0);
  await page.getByRole("button", { name: /^(Reports|报告|运行记录)$/ }).click();
  await expect(pageVaultSwitch).toHaveValue("personal");
  await expect(page.locator(".app-route:not([hidden]) .report-vault-filter")).toHaveCount(0);
  await page.getByRole("button", { name: /^(Tokens|令牌|Token 分析)$/ }).click();
  await expect(pageVaultSwitch).toHaveValue("work");

  const hiddenTokenRequestCount = requestedUrls.filter((value) => new URL(value).pathname === "/tokens").length;
  await page.getByRole("button", { name: /^(Knowledge|知识)$/ }).click();
  await pageVaultSwitch.selectOption("personal");
  await page.waitForTimeout(50);
  expect(requestedUrls.filter((value) => new URL(value).pathname === "/tokens")).toHaveLength(hiddenTokenRequestCount);

  await page.getByRole("button", { name: /^(Chat|对话)$/ }).click();
  await expect(composer).toHaveValue("retain this draft");
  await expect(chatScope).toHaveValue("all");

  await page.getByRole("button", { name: /Work.*(New chat|新建对话)/ }).click();
  await expect(composer).toHaveValue("");
  await expect(chatScope).toHaveValue("work");
  await composer.fill("scope-bound draft");
  await chatScope.selectOption("all");
  await expect(composer).toHaveValue("");
  await expect(chatScope).toHaveValue("all");
});
