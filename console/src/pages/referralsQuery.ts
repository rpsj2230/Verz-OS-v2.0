/**
 * What the Referred to me screen asks the API for and sends it. No React.
 *
 * `brain.compliance_routes.my_referrals` answers with the referrals routed to the caller and no
 * others, and the database decides which (migration 0104's policy), so this module filters nothing
 * and needs no capability: the person named for a topic has to be able to read what was sent to
 * them without somebody first granting them a screen.
 *
 * **A referral carries no question, and nothing here asks for one.** It says who asked, when and
 * about which topic, because that is all the interception keeps: what was written never left the
 * conversation it was written in.
 *
 * Task ids: M24.2.2
 */

import type { components } from "../api/schema";

export type ReferralsAnswer = components["schemas"]["ReferralsView"];
export type Referral = components["schemas"]["ReferralView"];

export const REFERRALS_API_PATH = "/me/referrals";

/** Where one referral is marked handled. */
export function handledApiPath(referralId: string): string {
  return `${REFERRALS_API_PATH}/${encodeURIComponent(referralId)}/handled`;
}

/** Where one referral stands, in one sentence. `at` renders an instant the page's way. */
export function referralState(one: Referral, at: (instant: string) => string): string {
  if (one.handled_at === null) {
    return "Not handled yet.";
  }
  return one.handled_by === null ? `Handled at ${at(one.handled_at)}.` : `Handled at ${at(one.handled_at)} by ${one.handled_by}.`;
}
