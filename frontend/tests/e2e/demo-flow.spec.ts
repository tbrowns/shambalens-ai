import { expect, test } from "@playwright/test";
import { assessment, initialAssessment } from "../fixtures";

test("demo assessment reaches a visibly simulated verified report", async ({ page }) => {
  const created = {
    ...assessment,
    status: "created",
    image_quality: null,
    model_observation: null,
    initial_assessment: null,
    answers: null,
    final_assessment: null,
    verification: null,
    completed_at: null,
  };
  const analyzed = {
    ...created,
    status: "questions_ready",
    image_quality: initialAssessment.image_quality,
    initial_assessment: initialAssessment,
  };
  let current: object = created;
  const cors = {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type,x-shamba-token",
  };

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors });
      return;
    }
    if (path.endsWith("/system/runtime")) {
      await route.fulfill({ json: { ai_provider: "demo", execution_mode: "demo", vision_model: "deterministic-fixture", reasoning_model: "deterministic-fixture", verifier_model: "deterministic-fixture", last_stage_latencies_ms: {}, database: "postgresql", image_storage: "local" }, headers: cors });
      return;
    }
    if (path.endsWith("/assessments") && request.method() === "POST") {
      current = created;
      await route.fulfill({ status: 201, json: current, headers: cors });
      return;
    }
    if (path.endsWith("/analyze")) {
      current = analyzed;
      await route.fulfill({ json: current, headers: cors });
      return;
    }
    if (path.endsWith("/answers")) {
      current = assessment;
      await route.fulfill({ json: current, headers: cors });
      return;
    }
    if (path.includes(`/assessments/${assessment.id}`)) {
      await route.fulfill({ json: current, headers: cors });
      return;
    }
    await route.fulfill({ status: 404, json: { error: { code: "not_found", message: "Not found", retryable: false, request_id: "e2e" } }, headers: cors });
  });

  await page.goto("/assessment");
  await expect(page.getByText("Demo mode — results are simulated and clearly marked.")).toBeVisible();
  await page.getByRole("button", { name: /Tomato leaf spots/ }).click();
  await page.getByRole("button", { name: "Continue to context" }).click();
  await page.getByRole("button", { name: /Analyze with evidence/ }).click();

  await expect(page).toHaveURL(new RegExp(`/assessment/${assessment.id}$`));
  await expect(page.getByRole("heading", { name: "A few questions that matter" })).toBeVisible();
  await page.getByRole("radio", { name: "No", exact: true }).check({ force: true });
  await expect(page.getByRole("radio", { name: "No", exact: true })).toBeChecked();
  await page.getByRole("radio", { name: "Mostly lower leaves" }).check({ force: true });
  await expect(page.getByRole("radio", { name: "Mostly lower leaves" })).toBeChecked();
  await page.getByRole("textbox", { name: "How many plants are affected?" }).fill("Three plants");
  await page.getByRole("button", { name: "Get verified plan" }).click();

  await expect(page).toHaveURL(new RegExp(`/report/${assessment.id}$`));
  await expect(page.getByRole("heading", { name: assessment.final_assessment!.most_likely_explanation })).toBeVisible();
  await expect(page.getByText("Simulated demo — not live AI analysis")).toBeVisible();
  await page.getByText("AI system & provenance").click();
  await expect(page.getByText("Independent verification passed")).toBeVisible();
});

test("landing and safety routes render", async ({ page }) => {
  await page.route("**/api/v1/system/runtime", (route) => route.fulfill({ json: { ai_provider: "groq", execution_mode: "live", vision_model: "qwen/qwen3.8-27b", reasoning_model: "openai/gpt-oss-120b", verifier_model: "openai/gpt-oss-120b", last_stage_latencies_ms: {}, database: "postgresql", image_storage: "local" }, headers: { "access-control-allow-origin": "*" } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /See what your crop is telling you/ })).toBeVisible();
  await page.goto("/about");
  await expect(page.getByRole("heading", { name: "How ShambaLens works" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Important limits" })).toBeVisible();
});
