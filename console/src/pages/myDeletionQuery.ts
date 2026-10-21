/**
 * What the deletion card in My workspace and the waiting-asks list on Retention ask the API for.
 * No React.
 *
 * `brain.member_deletion_routes` answers for the person asking and nobody else: neither request
 * takes a parameter naming a person. Asking records an ask and deletes nothing, and the answer says
 * so; the four lists are the retention policy's own, drawn as they were sent.
 *
 * Task ids: M40.4.2.3
 */

import type { components } from "../api/schema";

export type MyDeletion = components["schemas"]["MyDeletionView"];
export type DeletionRoute = components["schemas"]["MemberDeletionRouteView"];
export type StoreLine = components["schemas"]["MemberDeletionStoreLineView"];
export type WaitingAsks = components["schemas"]["MemberDeletionWaitingAsksView"];

/** `brain.member_deletion_routes`: read to see the lists and one's own ask, posted to ask. */
export const MY_DELETION_API_PATH = "/me/deletion-request";

/** The waiting asks, for the holder of the erasure authority. */
export const WAITING_ASKS_API_PATH = "/govern/erasure-requests";
