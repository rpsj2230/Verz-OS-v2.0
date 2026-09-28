/**
 * The shapes of what the console audit claims about a screen's writes, the helpers that spell a
 * claim, and the proofs more than one module cites.
 *
 * **Only what two modules share lives here.** A module's own writes, reads and proofs sit in its
 * file under `consoleAudit/`, so a console change edits its own module's file and no other. This is
 * the remainder, and the module files import it, never `consoleAudit.ts`: that file reads every
 * module file eagerly, so a module file importing it back would read its constants before they
 * exist.
 *
 * Task ids: M27.8.1, M27.8.17
 */

/**
 * A read a screen makes only once a person has done something. `versioned` is false for a read
 * served at the root, as the setup routes are, rather than under `/api/v1`.
 */
export interface ReadAfterAnAction {
  readonly screen: string;
  readonly spelled: string;
  readonly built: string;
  readonly versioned?: boolean;
}

/** One write a screen sends: the call's key in `support/writes.ts`, and every route it can reach. */
export interface WriteRoute {
  readonly route: string;
  /** The address the call builds, from the function or constant that spells it. */
  readonly spelled: string;
  readonly built: string;
  /** False for the two setup routes, which live at the root rather than under `/api/v1`. */
  readonly versioned: boolean;
}

/** A case or referral id to build a compliance address with; the routes take a UUID. */
export const COMPLIANCE_CASE = "11111111-2222-4333-8444-555555555555";

export function at(route: string, spelled: string, built: string, versioned = true): WriteRoute {
  return { route, spelled, built, versioned };
}

/** A named Python test that asserts one of the three, or why there is none. */
export type Proof =
  | { readonly test: string; readonly database: boolean }
  | { readonly none: string; readonly leaf?: string }
  | { readonly notApplicable: string };

export interface Proofs {
  readonly row: Proof;
  readonly audit: Proof;
  readonly behaviour: Proof;
}

export function t(file: string, name: string, database = false): Proof {
  return { test: `tests/unit/${file}.py::${name}`, database };
}

/** `tests/unit/test_console_control_audit.py`, which presses these controls against PostgreSQL. */
export function audited(name: string): Proof {
  return t("test_console_control_audit", name, true);
}

export const SETTINGS_PRESSED = audited("test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick");

export const A_SETTING_ENTRY_NO_TEST_FOLLOWS: Proof = {
  none: "The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry.",
};

export const A_BINDING_CHANGE_IS_AUDITED = t(
  "test_channel_binding",
  "test_each_bind_rebind_and_unbind_leaves_its_entry_and_the_chain_verifies",
  true,
);
