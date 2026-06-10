import { expect, test } from "@playwright/test";

test("management console renders core navigation", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/KnoArbor Console/);
  await expect(page.getByRole("button", { name: /^(Overview Status and next actions|总览 状态与下一步)$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Ingest multi-source information|将多源信息编译/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Update Settings|更新设置/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "GitHub" })).toBeVisible();

  await page.getByRole("button", { name: /^(Workspace Settings|工作区设置)$/ }).click();
  await expect(page.getByRole("dialog").getByText(/Workspace Settings|工作区设置/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Save Settings|保存设置/ })).toBeVisible();
  await expect(page.getByRole("dialog").locator("h2").filter({ hasText: /Vault|知识库/ }).first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByRole("button", { name: /^(Graph Explore links|知识图谱 查看页面关系)$/ }).click();
  await expect(page.locator("main").getByText(/Graph|知识图谱/).first()).toBeVisible();
  await expect(page.getByText(/Directory mix|目录分布|Graph data is loading|正在加载知识图谱|Loading/)).toBeVisible();
});
