import { expect, test } from "@playwright/test";

// Beta (2026-11-28): «Report a problem» copia o guarda el informe que el tester ve, y el
// asistente guarda solo las claves tecleadas sin volver a mostrarlas.

test("the report preview follows the note and Copy report copies exactly what is shown", async ({ page }) => {
  await page.goto("/e2e/beta-help-harness.html");

  const dialog = page.getByRole("dialog", { name: "Report a problem" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Report contents")).toContainText('"active_tab": "risk"');
  await expect(dialog.getByText("Gamma does not send it anywhere.")).toBeVisible();

  await dialog.getByLabel("What happened?").fill("Risk froze after Open In Risk");
  await expect(dialog.getByLabel("Report contents")).toContainText('"note": "Risk froze after Open In Risk"');

  await dialog.getByRole("button", { name: "Copy report" }).click();
  await expect(dialog.getByRole("status")).toContainText("Report copied");
  const copied = await page.getByTestId("clipboard").textContent();
  expect(JSON.parse(copied ?? "{}").note).toBe("Risk froze after Open In Risk");
});

test("Save report shows where the file went", async ({ page }) => {
  await page.goto("/e2e/beta-help-harness.html");
  const dialog = page.getByRole("dialog", { name: "Report a problem" });

  await dialog.getByLabel("What happened?").fill("Saved note");
  await dialog.getByRole("button", { name: "Save report" }).click();

  await expect(dialog.getByRole("status")).toContainText("gamma-report-20261128T100000Z.json");
  await expect(page.getByTestId("calls")).toContainText("save:Saved note");
});

test("a clipboard failure says how to get the report another way", async ({ page }) => {
  await page.goto("/e2e/beta-help-harness.html?view=report-copy-fail");
  const dialog = page.getByRole("dialog", { name: "Report a problem" });
  await expect(dialog.getByLabel("Report contents")).toBeVisible();

  await dialog.getByRole("button", { name: "Copy report" }).click();

  await expect(dialog.getByRole("status")).toContainText("could not copy to the clipboard");
});

test("Escape closes the report dialog", async ({ page }) => {
  await page.goto("/e2e/beta-help-harness.html");
  await expect(page.getByRole("dialog", { name: "Report a problem" })).toBeVisible();

  await page.keyboard.press("Escape");

  await expect(page.getByTestId("closed")).toHaveText("closed");
});

test("Setup saves only the keys typed and clears the fields", async ({ page }) => {
  await page.goto("/e2e/beta-help-harness.html?view=wizard");

  const save = page.getByRole("button", { name: "Save key" });
  await expect(save).toBeDisabled();

  const fred = page.getByLabel("FRED_API_KEY");
  await expect(fred).toHaveAttribute("type", "password");
  await fred.fill("fred-test-0123456789");
  await save.click();

  await expect(page.getByTestId("calls")).toHaveText("keys:FRED_API_KEY");
  await expect(page.getByText("Restart Gamma to apply the change.")).toBeVisible();
  await expect(fred).toHaveValue("");

  // El foco queda dentro del diálogo, así que Escape sigue cerrándolo.
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("closed")).toHaveText("closed");
});
