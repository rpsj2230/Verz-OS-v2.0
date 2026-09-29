/**
 * Findings from the browser walk of the owner's install on 2026-09-29 that live in the console's
 * own words and parts, each held against what the walk saw.
 *
 * Each test names what was on the screen and what breaks if the test is deleted. The page-level
 * halves are in each page's own test file; these are the parts every page shares and the
 * sentences a page composes itself.
 *
 * Task ids: M27.10.2, M27.16.1
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, test, vi } from "vitest";
import { ConfirmDialog, Note, NOTE_LEADS } from "../src/components/kit";
import { actionConsequence, runIsGoing, type JobRow } from "../src/pages/jobsQuery";
import { passwordLabel, PASSWORD_LABEL, SET_PASSWORD_LABEL } from "../src/pages/notifications/RelayActs";
import { ACTIVITY_API_PATH } from "../src/pages/overview/overviewQuery";
import { QUALITY_LEDE } from "../src/pages/reports/QualityPage";
import { FRESHNESS_WORDS, freshnessWords } from "../src/pages/spendQuery";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

function job(overrides: Partial<JobRow> = {}): JobRow {
  return {
    control: "canary_run",
    keeps_true: "that the gate still refuses what it refused yesterday",
    every_seconds: 43200,
    destructive: false,
    report_only: false,
    runnable: true,
    needs: null,
    last_started_at: null,
    last_finished_at: null,
    last_outcome: null,
    last_report: null,
    last_failure_kind: null,
    last_succeeded_at: null,
    owed: false,
    late_by_seconds: null,
    paused: false,
    pause_changed_by: null,
    pause_changed_at: null,
    run_requested_at: null,
    run_requested_by: null,
    run_pending: false,
    ...overrides,
  } as JobRow;
}

describe("a confirmation after an act", () => {
  test("says the act was done and never that something works today", () => {
    // Seen: "Works today: "Look for newer releases" is now switched off." What breaks if this is
    // deleted: `done` can lead with the feature statement again, over a switch-off or a failure.
    const { container } = render(<Note kind="done">"Look for newer releases" is now switched off.</Note>);
    expect(NOTE_LEADS.done).toBe("");
    expect(container.textContent).toBe('"Look for newer releases" is now switched off.');
    expect(render(<Note kind="works">x</Note>).container.textContent).toBe(`${NOTE_LEADS.works}x`);
  });
});

describe("the confirm dialog's button", () => {
  test("is the danger button by default and the plain one for an act that is not a danger", () => {
    // Seen: switching a feature on used the danger button. What breaks if this is deleted: `danger`
    // is accepted and ignored, or every confirmation loses its danger colour.
    const props = { question: "Go?", consequence: "It goes.", cancelLabel: "Keep", onConfirm: vi.fn(), onCancel: vi.fn() };
    const { unmount } = render(<ConfirmDialog open {...props} confirmLabel="Remove" />);
    expect(screen.getByRole("button", { name: "Remove" }).getAttribute("data-variant")).toBe("destructive");
    unmount();
    render(<ConfirmDialog open {...props} confirmLabel="Switch on" danger={false} />);
    const plain = screen.getByRole("button", { name: "Switch on" });
    expect(plain.getAttribute("data-variant")).toBe("default");
    fireEvent.click(plain);
    expect(props.onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("a job's pause and its stop", () => {
  test("the pause confirmation is one sentence a person can read", () => {
    // Seen: "While it is paused, this is not kept true: that the gate still refuses ...". What
    // breaks if this is deleted: the garbled sentence comes back on every job's Pause.
    const said = actionConsequence("pause", job());
    expect(said).toContain("While it is paused, nothing makes sure that the gate still refuses what it refused yesterday.");
    expect(said).not.toContain("not kept true");
  });

  test("stopping is offered only while a run is going", () => {
    // Seen: a job that had never run offered "Stop the run". What breaks if this is deleted: the
    // page offers to stop a run that does not exist, beside a sentence saying it cannot.
    expect(runIsGoing(job())).toBe(false);
    expect(runIsGoing(job({ last_started_at: "2019-03-04T09:00:00Z" }))).toBe(true);
    expect(runIsGoing(job({ last_started_at: "2019-03-04T09:00:00Z", last_outcome: "ok" }))).toBe(false);
  });
});

describe("sentences a page composes", () => {
  test("the relay's password is set when none is held and replaced when one is", () => {
    // Seen: "Replace password" beside "No relay is saved". What breaks if this is deleted: the
    // label stops following whether a password is held.
    expect(passwordLabel(false)).toBe(SET_PASSWORD_LABEL);
    expect(passwordLabel(null)).toBe(SET_PASSWORD_LABEL);
    expect(passwordLabel(true)).toBe(PASSWORD_LABEL);
  });

  test("a spend report a day old is not called live", () => {
    // Seen: "freshness live" on a figure fourteen hours old. What breaks if this is deleted: the
    // Spend page shows the grade's raw word again, which a person reads as "up to the minute".
    for (const word of Object.values(FRESHNESS_WORDS)) {
      expect(word.toLowerCase()).not.toContain("live");
    }
    expect(freshnessWords("live")).toBe(FRESHNESS_WORDS["live"]);
    expect(freshnessWords("something new")).toBe("something new");
  });

  test("the Quality page says what a pass proved and not more", () => {
    // Seen: "a pass means every one was refused" while each run said no refusal was compared.
    // What breaks if this is deleted: the page claims a check the canary did not make.
    expect(QUALITY_LEDE).not.toContain("every one was refused");
    expect(QUALITY_LEDE).toContain("once answer rules are loaded");
  });

  test("the Dashboard's recent activity asks for changes only", () => {
    // Seen: six of six entries were "Answered a call about a credential". What breaks if this is
    // deleted: the card goes back to asking for every entry and is flooded by the vault's reads.
    const asked = new URL(ACTIVITY_API_PATH, "https://console.test");
    expect(asked.pathname).toBe("/audit");
    expect(asked.searchParams.get("changes_only")).toBe("true");
  });
});

describe("the Platform screens' two profiles", () => {
  test("Capacity calls the install's size its install size, and a size that declares nothing says so", async () => {
    // Seen: "PROFILE lite" beside "DECLARED BY THIS PROFILE 0 MiB", while Settings called the model
    // setting a profile too. What breaks if this is deleted: the word comes back for two things,
    // and nought is drawn for a figure the size never declared.
    const { mountPage, json } = await import("./support/pageHarness");
    const { DECLARES_NO_FIGURE, INSTALL_SIZE_LABEL } = await import("../src/pages/operations/CapacityPage");
    const capacity = (declared: number) => ({
      memory: { profile: "lite", host_total_mib: 11960, declared_mib: declared, deployed_mib: null, breaches: [], unbudgeted: [] },
      connections: [],
    });
    const load = async () => {
      const { Capacity } = await import("../src/pages/Capacity");
      return <Capacity />;
    };

    const nothing = await mountPage("/connections", load, { "GET /api/v1/install/capacity": () => json(capacity(0)) });
    const text = nothing.container.textContent ?? "";
    expect(text).toContain(INSTALL_SIZE_LABEL);
    expect(text).toContain(DECLARES_NO_FIGURE);
    expect(text).not.toMatch(/(^|[^\d,])0 MiB/);
    expect(text.toLowerCase()).not.toContain("profile");
  });
});
