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

  // F4: the D9 tab describes the D9 chart, not the D1 rising sign
  await page.getByRole("tab", { name: "D9 · Navamsa" }).click();
  await expect(page.getByText("D9 rising sign Libra.", { exact: false })).toBeVisible();
  await expect(page.getByText("Rising sign Leo at", { exact: false })).toHaveCount(0);
  await page.getByRole("tab", { name: "D1 · Birth chart" }).click();

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

test("the Chart Inspector opens from the chart and keeps its target (I1)", async ({ page, isMobile }) => {
  await page.goto("/");
  await page.getByRole("checkbox").first().check();
  await page.getByRole("button", { name: "Start as guest" }).click();
  await page.locator("#dd").fill("08"); await page.locator("#mm").fill("12"); await page.locator("#yy").fill("1984");
  await page.locator("#hh").fill("12"); await page.locator("#mi").fill("20"); await page.locator("#ap").selectOption("AM");
  await page.locator("#place").fill("Pune");
  await page.locator("#places").getByRole("option", { name: /Pune/ }).click();
  await page.getByRole("button", { name: "Reveal my chart" }).click();
  await expect(page).toHaveURL(/dashboard/, { timeout: 30_000 });

  await page.getByRole("button", { name: /^Jupiter in Sagittarius/ }).click();
  await expect(page).toHaveURL(/\?inspect=d1\.Jupiter/);
  const panel = page.getByRole("region", { name: "Inspector" });
  await expect(panel.getByText("Jupiter in your fifth house, in Sagittarius, its own sign.")).toBeVisible();
  await expect(panel.getByText("Dispositor chain")).toBeVisible();
  if (isMobile) await expect(panel.getByRole("button", { name: "Full", exact: true })).toBeVisible(); // bottom sheet on phones
  await axe(page);

  await panel.getByRole("button", { name: "Inspect Mercury" }).click();
  await expect(page).toHaveURL(/inspect=d1\.Mercury/);
  await page.getByRole("tab", { name: "D9 · Navamsa" }).click();
  await expect(page).toHaveURL(/inspect=d9\.Mercury/);
  await expect(panel.getByText(/^Mercury in your eighth house, in Taurus/)).toBeVisible();

  // I2: houses are buttons on the chart; an empty house is read through its lord
  await page.getByRole("tab", { name: "D1 · Birth chart" }).click();
  await page.getByRole("button", { name: "House seven, Aquarius, empty" }).click();
  await expect(page).toHaveURL(/inspect=d1\.h7/);
  await expect(panel.getByText("House seven is Aquarius. It is empty, so it is read through its lord.")).toBeVisible();
  await expect(panel.getByRole("heading", { name: "House seven · Aquarius" })).toBeVisible();
  await axe(page);
  await panel.getByRole("button", { name: "Inspect Saturn" }).click();
  await expect(page).toHaveURL(/inspect=d1\.Saturn/);

  await page.goBack(); // Back closes the Inspector in one step, however many targets were visited
  await expect(page).not.toHaveURL(/inspect=/);
  await expect(page.getByRole("region", { name: "Inspector" })).toHaveCount(0);
});

