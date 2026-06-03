import { expect, test } from "@playwright/test";

test("management console renders core navigation", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/KnoArbor Console/);
  await expect(page.getByRole("button", { name: /^(Overview Status and next actions|总览 状态与下一步)$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Ingest multi-source information|将多源信息编译/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Update Settings|更新设置/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "GitHub" })).toBeVisible();

  await page.getByRole("button", { name: /^(Settings Runtime config|设置 配置运行环境)$/ }).click();
  await expect(page.locator("main").getByText(/Settings|设置/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Save Settings|保存设置/ })).toBeVisible();
  await expect(page.locator("h2").filter({ hasText: /Knowledge base|知识库/ }).first()).toBeVisible();

  await page.getByRole("button", { name: /^(Graph Explore links|知识图谱 查看页面关系)$/ }).click();
  await expect(page.locator("main").getByText(/Graph|知识图谱/).first()).toBeVisible();
  await expect(page.getByText(/Page link graph|页面关系图|Graph data is loading|图谱数据加载中/)).toBeVisible();
});
