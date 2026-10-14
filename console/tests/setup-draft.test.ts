/**
 * What the wizard keeps as it goes and what it reads back (M42.5.12): the body cut at the screen
 * just finished, and the screen a kept draft resumes at.
 *
 * Task ids: M42.5.12, M27.15.68
 */

import { describe, expect, test } from "vitest";
import { SCREENS, appointmentBody, draftBody, readDraft, type DraftView } from "../src/setup/wizard";

const answers = {
  company: { company_name: "A company", web_address: "https://company.example.invalid" },
  administrator: { full_name: "Ada", work_address: "ada@company.example.invalid" },
};

describe("the body that keeps the draft", () => {
  test("holds the screens up to the one just finished and none after it", () => {
    const body = draftBody("code", answers, new Set(), "company");
    expect(Object.keys(body.answers ?? {})).toEqual(["company"]);
    expect(body.setup_code).toBe("code");
  });

  test("holds a skipped screen only once it has been reached", () => {
    const skipped = new Set(["connections" as const]);
    expect(draftBody("code", answers, skipped, "company").skipped).toEqual([]);
    expect(draftBody("code", answers, skipped, "connections").skipped).toEqual(["connections"]);
  });
});

describe("what the draft never carries", () => {
  test("a secret answer is blanked in the body that keeps the draft and kept in the one that appoints", () => {
    // What breaks if this is deleted: a provider key sent to a route whose only job is to remember
    // the person's place. The server drops a credential on the way in, and this holds that the console
    // does not send it, while the appointment, which has to carry it, still does.
    const typed = {
      ...answers,
      model_provider: { model_profile: "hosted", model_provider: "anthropic", provider_key: "sk-SENTINEL-1" },
    };
    const kept = draftBody("code", typed, new Set(), "model_provider");
    expect(kept.answers?.["model_provider"]).toEqual({
      model_profile: "hosted",
      model_provider: "anthropic",
      provider_key: "",
    });
    expect(JSON.stringify(kept)).not.toContain("sk-SENTINEL-1");
    const appointed = appointmentBody("code", typed, new Set());
    expect(appointed.answers?.["model_provider"]).toMatchObject({ provider_key: "sk-SENTINEL-1" });
  });
});

describe("reading a kept draft", () => {
  const view = (kept: Partial<DraftView>): DraftView => ({
    answers: {},
    skipped: [],
    next_step: null,
    ...kept,
  });

  test("nothing kept resumes nowhere", () => {
    expect(readDraft(view({}))).toBeNull();
  });

  test("a kept draft resumes at the screen the server names", () => {
    const found = readDraft(view({ answers: answers, next_step: "data_steward" }));
    expect(found?.answers).toEqual(answers);
    expect(SCREENS[found?.at ?? -1]?.key).toBe("data_steward");
  });

  test("a next screen this console does not know resumes after the setup code", () => {
    expect(readDraft(view({ answers: answers, next_step: null }))?.at).toBe(1);
  });
});
