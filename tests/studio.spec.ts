import { expect, test } from "@playwright/test";

test("upload controls and completed result work end to end", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Local worker hidup")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analisis dan potong clip" })).toBeDisabled();
  await page.getByRole("button", { name: "Upload fail" }).click();

  const firstChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Pilih video" }).click();
  await (await firstChooser).setFiles({
    name: "demo.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("demo"),
  });

  await expect(page.getByText("demo.mp4")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analisis dan potong clip" })).toBeDisabled();
  await page.getByRole("button", { name: "Tukar video" }).click();
  await expect(page.getByRole("button", { name: "Pilih video" })).toBeVisible();

  const secondChooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Pilih video" }).click();
  await (await secondChooser).setFiles({
    name: "demo.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("demo"),
  });

  await page.getByRole("button", { name: "Selesai" }).click();
  await expect(page.getByText("UPLOAD SELESAI")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analisis dan potong clip" })).toBeEnabled();

  await page.getByLabel("Bilangan clip").last().fill("3");
  await page.getByLabel("Panjang clip").last().selectOption("20-40");
  await page.getByLabel("Bahasa audio").last().selectOption("ms");
  await page.getByRole("button", { name: "Analisis dan potong clip" }).click();

  await expect(page.getByRole("heading", { name: "Clip dah siap." })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("heading", { name: "Ramai silap dekat bahagian ini" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download MP4" })).toHaveAttribute(
    "href",
    "http://localhost:8787/outputs/demo1234/clip-01.mp4",
  );
  await expect(page.getByRole("link", { name: "Download SRT" })).toHaveAttribute(
    "href",
    "http://localhost:8787/outputs/demo1234/clip-01.srt",
  );
  await expect(page.getByRole("link", { name: "Download semua (.zip)" })).toBeVisible();

  await page.getByRole("button", { name: "Potong video lain" }).click();
  await expect(page.getByRole("button", { name: "Pilih video" })).toBeVisible();
});

test("YouTube URL can be inspected before starting a job", async ({ page }) => {
  await page.goto("/");

  await page.getByLabel("URL YouTube").fill("https://youtu.be/demo");
  await page.getByRole("button", { name: "Semak video" }).click();

  await expect(page.getByRole("heading", { name: "Podcast bisnes tanpa jargon" })).toBeVisible();
  await expect(page.getByText("Studio Demo · 12:34")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analisis dan potong clip" })).toBeEnabled();
});

test("mobile layout has no horizontal overflow and keeps controls tappable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  const urlInput = page.getByLabel("URL YouTube");
  const box = await urlInput.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);

  await page.getByRole("button", { name: "Upload fail" }).click();
  const choose = page.getByRole("button", { name: "Pilih video" });
  const chooseBox = await choose.boundingBox();
  expect(chooseBox?.height ?? 0).toBeGreaterThanOrEqual(44);

  await expect(page.getByText("Tetapan").first()).toBeVisible();
  await expect(page.getByLabel("Panjang clip").first()).toBeVisible();
});
