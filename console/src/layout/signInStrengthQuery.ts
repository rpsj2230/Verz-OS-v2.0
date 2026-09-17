/**
 * What the shell reads out of `GET /me` to say what a sign-in without a second factor costs. No
 * React.
 *
 * `brain.api_routes.CallerView` carries two facts for this, and they are the caller's own: the verbs
 * they hold grants for and cannot use at this sign-in's assurance, and whether signing in again with
 * a second factor would give at least one back. Until 2026-09-17 the first a person learned of it
 * was a screen answering "I could not find that" for work they hold, because a refusal for weak
 * assurance is the same 404 as every other refusal. The banner says it before anything fails.
 *
 * **Typed here rather than from the generated schema, and read field by field.** The two fields
 * were added to the API in the same change as this module, by a different hand, and a console
 * typed against a document generated before that change would not build. Each field is read back
 * through a `typeof` check, so a body without them is a body with nothing withheld, and a body from
 * an older API draws no banner rather than a wrong one.
 *
 * **The verbs are named in words and never as capabilities.** The API sends verbs and not the
 * capability strings or the scopes they were granted over, because a verb is a fact about the
 * caller and a scope is a fact about the company. `VERB_WORDS` has a phrase for every verb
 * `brain.core.entitlement.VERBS` declares, which `tests/second-factor.test.tsx` holds against the
 * Python, and a verb it has no phrase for is named as itself rather than dropped.
 *
 * Task ids: M27.9.2
 */

/** Where the shell asks, under the API base. The Overview reads the same address for its own facts. */
export const ME_API_PATH = "/me";

/** The banner's heading. */
export const THIS_SIGN_IN_HAS_NO_SECOND_FACTOR = "This sign-in has no second factor";

/** What the banner says first, in plain words. */
export const ADMINISTRATION_NEEDS_A_SECOND_FACTOR =
  "Administration and approvals need a sign-in with a second factor, and this sign-in has none.";

/** A phrase for each verb a grant can carry, from `brain.core.entitlement.VERBS`. */
export const VERB_WORDS: Readonly<Record<string, string>> = Object.freeze({
  read: "reading",
  write: "changing records",
  invoke: "running agents and tools",
  approve: "approvals",
  admin: "administration",
});

/** The two facts the banner is drawn from. */
export interface SignInStrength {
  readonly secondFactorNeeded: boolean;
  readonly withheldVerbs: readonly string[];
}

const NOTHING_WITHHELD: SignInStrength = Object.freeze({ secondFactorNeeded: false, withheldVerbs: [] });

/** Read the two facts out of a `/me` body, or nothing withheld when the body does not carry them. */
export function readSignInStrength(payload: unknown): SignInStrength {
  if (typeof payload !== "object" || payload === null) {
    return NOTHING_WITHHELD;
  }
  const { second_factor_needed: needed, withheld_verbs: verbs } = payload as Record<string, unknown>;
  return {
    // Exactly true, as `api/errors.THE_SECOND_FACTOR_IS_READ_FROM_ITS_FLAG` reads the failure's.
    secondFactorNeeded: needed === true,
    withheldVerbs: Array.isArray(verbs) ? verbs.filter((one): one is string => typeof one === "string" && one !== "") : [],
  };
}

/** The withheld verbs in words, joined as a sentence joins a list: "a", "a and b", "a, b and c". */
export function verbsInWords(verbs: readonly string[]): string {
  const words = [...new Set(verbs.map((one) => VERB_WORDS[one] ?? one))];
  if (words.length <= 1) {
    return words[0] ?? "";
  }
  return `${words.slice(0, -1).join(", ")} and ${words.at(-1) ?? ""}`;
}

/** The second sentence: what stays withheld until the person signs in again. Empty for no verbs. */
export function withheldSentence(verbs: readonly string[]): string {
  const words = verbsInWords(verbs);
  return words === "" ? "" : `Until you sign in again with it, what you hold for ${words} is withheld.`;
}
