import { expect, test, type Page } from "@playwright/test";

const GUIDE = "Solar Panel Maintenance Guide. Solar panels should be cleaned every month to remove dust. " +
  "Inverters should be inspected once a year by a qualified technician.";

async function uploadGuide(page: Page, name = "solar-guide.txt") {
  await page.goto("/app/library");
  await page.locator("input[type=file]").first().setInputFiles({ name, mimeType: "text/plain", buffer: Buffer.from(GUIDE) });
  await expect(page.getByText(name, { exact: true })).toBeVisible({ timeout: 30_000 });
}

test("landing page leads into the app and the legal pages", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Answers from your documents/ })).toBeVisible();
  await page.goto("/privacy");
  await expect(page.getByRole("heading", { name: "Privacy notice" })).toBeVisible();
  await page.goto("/");
  await page.getByRole("link", { name: "Open AfriSearch" }).first().click();
  await expect(page).toHaveURL(/\/app/);
});

test("upload, ask, cite, rate", async ({ page }) => {
  await uploadGuide(page);
  await page.getByRole("button", { name: "New chat" }).first().click();
  const box = page.getByLabel("Your question");
  await box.fill("How often should solar panels be cleaned?");
  await box.press("Enter");

  await expect(page.getByText("Clean them every month")).toBeVisible();
  await page.locator("button[title='Show source S1']").click();
  await expect(page.locator("#source-S1")).toContainText("cleaned every month");
  await page.getByRole("button", { name: "Helpful", exact: true }).click();
  await expect(page.getByText("Thanks for the feedback")).toBeVisible();

  await expect(page).toHaveURL(/\/app\/chat\//);  // the chat was saved
  await page.getByRole("link", { name: "Insights" }).click();
  await expect(page.getByText("Questions per day")).toBeVisible();
});

test("passages-only search sends nothing to a model", async ({ page }) => {
  await uploadGuide(page, "guide-2.txt");
  await page.getByRole("button", { name: "New chat" }).first().click();
  await page.getByRole("button", { name: "Answer model" }).click();
  await page.getByText("Find passages only", { exact: true }).click();
  const box = page.getByLabel("Your question");
  await box.fill("When should inverters be inspected?");
  await box.press("Enter");
  await expect(page.locator("[id$='-S1'] #source-S1")).toContainText("inspected once a year");
  await expect(page.getByText("Clean them every month")).toHaveCount(0);
});

test("dialogs keep keyboard focus inside", async ({ page }) => {
  await page.goto("/app/settings");
  await page.getByRole("button", { name: "Delete all my data" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  for (let i = 0; i < 6; i++) await page.keyboard.press("Tab");
  expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});
