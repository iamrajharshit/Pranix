// SPDX-License-Identifier: AGPL-3.0-only
// Guest flow smoke (F1): entry → age gate → birth form → dashboard with all cards, plus axe
// (WCAG 2.2 AA) on each screen. The sample birth is the invented one used across the docs.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function axe(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  const serious = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.length} nodes`)).toEqual([]);
}

test("guest reaches a complete dashboard and every screen passes axe", async ({ page }) => {
  await page.goto("/");
  await axe(page);
  await page.getByRole("checkbox").first().check();
  await page.getByRole("button", { name: "Start as guest" }).click();

  await expect(page.locator("#dd")).toBeVisible();
  await axe(page);
  await page.locator("#dd").fill("08");
  await page.locator("#mm").fill("12");
  await page.locator("#yy").fill("1984");
  await page.locator("#hh").fill("12");
  await page.locator("#mi").fill("20");
  await page.locator("#ap").selectOption("AM");
  await page.locator("#place").fill("Pune");
  await page.locator("#places").getByRole("option", { name: /Pune/ }).click();
  await page.getByRole("button", { name: "Reveal my chart" }).click();

  await expect(page).toHaveURL(/dashboard/, { timeout: 30_000 });
  await expect(page.locator("article.card")).toHaveCount(12, { timeout: 30_000 });
  await expect(page.getByText("Leo").first()).toBeVisible();
  await axe(page);

  // D80: a rule-selected card now opens a structured AI reading (fake provider in e2e)
  await page.locator("#more-birthstar").click();
  await expect(page.getByRole("heading", { name: "What it means for you" })).toBeVisible();
  await expect(page.getByText("Reflect", { exact: true })).toBeVisible();
  await expect(page.locator(".page").getByText("AI-phrased")).toBeVisible();
  await expect(page.locator("article.card .b-ai")).toHaveCount(12); // every card is now AI-written
  await axe(page);

  // Next, Next, then "Back to your map" must close the reading in one click (owner's bug, 25 Nov)
  await page.getByRole("button", { name: /Next/ }).click();
  await page.getByRole("button", { name: /Next/ }).click();
  await expect(page).toHaveURL(/#reading=/);
  await page.getByRole("button", { name: "Back to your map" }).click();
  await expect(page).not.toHaveURL(/#reading=/);
  await expect(page.locator(".page")).toHaveCount(0);
  await expect(page.locator("article.card")).toHaveCount(12);
});

test("the API serves the security headers the app relies on", async ({ request }) => {
  const r = await request.get("/");
  expect(r.headers()["content-security-policy"]).toBeTruthy();
});
