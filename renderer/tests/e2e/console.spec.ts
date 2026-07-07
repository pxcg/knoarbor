import { expect, test } from "@playwright/test";

test("management console renders core navigation", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/KnoArbor Console/);
  await expect(page.getByRole("button", { name: /^(Chat Ask your wiki|对话 询问知识库)$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^(Flows Run, ingest, lint|流程 运行、编译、维护)$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^(Knowledge Pages and graph|知识 页面与图谱)$/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "GitHub" })).toBeVisible();

  await page.getByRole("button", { name: /^(Workspace Settings|工作区设置)$/ }).click();
  await expect(page.getByRole("dialog").getByText(/Workspace Settings|工作区设置/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Save Settings|保存设置/ })).toBeVisible();
  await expect(page.getByRole("dialog").locator("h2").filter({ hasText: /Vault|知识库/ }).first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByRole("button", { name: /^(Knowledge Pages and graph|知识 页面与图谱)$/ }).click();
  await page.getByRole("button", { name: /^(Graph Explore links|知识图谱 查看页面关系)$/ }).click();
  await expect(page.locator("main").getByText(/Graph|知识图谱/).first()).toBeVisible();
  await expect(page.getByText(/Directory mix|目录分布|Graph data is loading|正在加载知识图谱|Loading/)).toBeVisible();
});
