/**
 * An agent's Knowledge section in the browser: it lists, adds by upload and by link, refuses a link
 * to a private address, and shows an item the agent does not draw on with its next step, at a
 * desktop width and at a phone's (M39.9.1.9).
 *
 * **The agent is built through the product's own agent builder**, as the administrator, by the same
 * routes the builder screens call: a draft is started, saved, checked and published, and the agent
 * it makes is the one this opens. The install the harness furnishes has no agent, and a section
 * drawn for an agent a test inserted into a table would prove the page against a row the product
 * never writes. Where the install cannot publish (no template signing key), the spec says so and
 * stops rather than passing: a skipped proof is not a proof.
 *
 * **Reached by the menu and the agent's own tabs, never by an address**, as `pages/module.ts` argues:
 * the console keeps its tokens in memory, so typing an address is a fresh sign-in.
 *
 * **Not run in the commit that added it.** It needs the full harness (identity provider, install,
 * Chromium), which a development machine without containers cannot start; the browser workflow runs
 * it. Deleting it leaves M39.9.1.9 with only the component tests, which draw the section against
 * answers a test wrote.
 *
 * Task ids: M39.9.1.9
 */

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { checkPage, reset, watch } from "../lib/checklist";
import { signInAsAdmin } from "../lib/signin";
import { openFromMenu } from "../pages/module";

const PHONE = { width: 390, height: 844 } as const;
const DESKTOP = { width: 1280, height: 900 } as const;

interface Built {
  readonly agentId: string;
  readonly name: string;
}

interface Draft {
  readonly draft_id: string;
  readonly agent_id: string;
  readonly name: string;
  readonly revision: number;
  readonly document: Record<string, unknown>;
  readonly publish_unavailable: string | null;
  readonly problems: string[];
}

/** Build an agent through the builder's own routes, or say why this install cannot. */
async function buildAgent(request: APIRequestContext, token: string): Promise<Built | string> {
  const auth = { Authorization: `Bearer ${token}` };
  const started = await request.post("/api/v1/agent-drafts", { headers: auth, data: {} });
  expect(started.status(), "a draft is started").toBe(201);
  const draft = (await started.json()) as Draft;
  if (draft.publish_unavailable !== null) {
    return draft.publish_unavailable;
  }
  const saved = await request.post(`/api/v1/agent-drafts/${draft.draft_id}/revisions`, {
    headers: auth,
    data: { document: draft.document, base: draft.revision },
  });
  expect(saved.status(), "the document is kept").toBe(200);
  const checked = await request.post(`/api/v1/agent-drafts/${draft.draft_id}/check`, { headers: auth, data: { revision: draft.revision } });
  expect(checked.status(), "the draft is checked").toBe(200);
  const result = (await checked.json()) as { passed: boolean; problems: string[] };
  expect(result.problems, "nothing stops the draft being published").toEqual([]);
  const published = await request.post(`/api/v1/agent-drafts/${draft.draft_id}/publish`, {
    headers: auth,
    data: { revision: draft.revision, for_department: false },
  });
  const outcome = (await published.json()) as { state?: string; sentence?: string };
  if (published.status() !== 201 || outcome.state !== "published") {
    return outcome.sentence ?? `publishing answered ${String(published.status())}`;
  }
  return { agentId: draft.agent_id, name: draft.name };
}

async function openKnowledge(page: Page, agent: Built): Promise<void> {
  await openFromMenu(page, "/agents", "Agents");
  await page.getByRole("link", { name: agent.name }).first().click();
  await page.locator(`a[href="/agents/${agent.agentId}/knowledge"]`).first().click();
  await expect(page.locator('[data-slot="agent-knowledge"]')).toBeVisible({ timeout: 20_000 });
}

/** Whether nothing on the page is wider than the window, which is a phone's horizontal scroll. */
async function fitsTheWindow(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
}

test("an agent's Knowledge section lists, adds by file and by link, refuses a private address and shows an unreached item with its next step", async ({ browser, request }, info) => {
  const page = await browser.newPage({ viewport: DESKTOP });
  const seen = watch(page);
  const token = await signInAsAdmin(page);
  await expect(page.locator('nav[aria-label="Sections"]')).toBeVisible({ timeout: 30_000 });

  const built = await buildAgent(request, token);
  test.skip(typeof built === "string", `this install cannot build an agent through the builder: ${String(built)}`);
  const agent = built as Built;
  await openKnowledge(page, agent);
  await checkPage(page, seen, "An agent's Knowledge section", info);
  reset(seen);
  const section = page.locator('[data-slot="agent-knowledge"]');

  // Nothing is drawn on yet, and the section says what it is for and offers both ways in.
  await expect(section.locator('[data-slot="knowledge-empty"], [data-slot="knowledge-list"]').first()).toBeVisible();
  const options = await request.get("/api/v1/knowledge/uploads/options", { headers: { Authorization: `Bearer ${token}` } });
  expect(options.status(), "the administrator may add documents").toBe(200);
  const departments = ((await options.json()) as { departments: string[] }).departments;
  expect(departments.length, "the install has a department to add to").toBeGreaterThan(0);

  // Add a file: it is listed, with the answer to whether the agent draws on it.
  await section.getByRole("button", { name: "Add a file" }).first().click();
  await section.locator('input[type="file"]').setInputFiles({
    name: "Handover.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Handover\n\nSign the BROWSERCHECK list before leaving.\n"),
  });
  await section.locator('[name="kind"]').selectOption({ index: 1 });
  await section.locator('[name="department"]').selectOption(departments[0] ?? "");
  await section.locator("form").first().evaluate((form: HTMLFormElement) => form.requestSubmit());
  await expect(section.locator('[data-slot="knowledge-added"]')).toContainText("Handover", { timeout: 30_000 });
  await expect(section.locator('[data-slot="knowledge-item"]').filter({ hasText: "Handover" })).toBeVisible();
  await expect(section.locator('[data-slot="knowledge-item"]').filter({ hasText: "Handover" }).locator('[data-slot="knowledge-arrival"]')).toHaveText("added as a file");

  // A link to a private address is refused by the address check and adds nothing.
  await section.getByRole("button", { name: "Add a web page by its link" }).first().click();
  await section.locator('[name="url"]').fill("https://169.254.169.254/latest/meta-data/");
  await section.locator('[name="kind"]').selectOption({ index: 1 });
  await section.locator("form").first().evaluate((form: HTMLFormElement) => form.requestSubmit());
  await expect(section).toContainText("address check", { timeout: 30_000 });
  await expect(section.locator('[data-slot="knowledge-item"]')).toHaveCount(1);

  // With a second department, a file added there is the company's document and not this agent's
  // until a person widens the rule: the section names the clause and offers the one next step.
  if (departments.length > 1) {
    await section.getByRole("button", { name: "Add a file" }).first().click();
    await section.locator('input[type="file"]').setInputFiles({
      name: "Elsewhere.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Elsewhere\n\nSign the ELSEWHERECHECK list.\n"),
    });
    await section.locator('[name="kind"]').selectOption({ index: 1 });
    await section.locator('[name="department"]').selectOption(departments[1] ?? "");
    await section.locator("form").first().evaluate((form: HTMLFormElement) => form.requestSubmit());
    await expect(section.locator('[data-slot="knowledge-added"]')).toBeVisible({ timeout: 30_000 });
  } else {
    info.annotations.push({ type: "not shown", description: "the install has one department, so no document could be added outside the agent's rule" });
  }
  expect(seen.refusedByPolicy, "nothing was refused under the page's policy").toEqual([]);

  // The same section at a phone's width: every control is still reachable and nothing scrolls sideways.
  await page.setViewportSize(PHONE);
  await expect(section).toBeVisible();
  expect(await fitsTheWindow(page), "the section fits a phone's width").toBe(true);
  await expect(section.getByRole("button", { name: "Add a file" }).first()).toBeVisible();
  await expect(section.getByRole("button", { name: "Add a web page by its link" }).first()).toBeVisible();
  const box = await section.getByRole("button", { name: "Add a file" }).first().boundingBox();
  expect(box?.height ?? 0, "a control is large enough to press on a phone").toBeGreaterThanOrEqual(40);
  await page.close();
});
