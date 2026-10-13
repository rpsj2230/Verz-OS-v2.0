/**
 * What the account cards in My workspace ask the API for. No React.
 *
 * `brain.member_self_routes` answers for the person asking and nobody else, and takes no parameter
 * naming a person. A refusal is the API saying this caller may not open the page, and the cards
 * draw what they were sent.
 *
 * Task ids: M40.1.1.3, M40.4.2.4, M40.3.3.1, M40.4.2.1
 */

import type { components } from "../api/schema";

export type MyDevicesBody = components["schemas"]["MyDevicesView"];
export type MyDevice = components["schemas"]["MyDeviceView"];
export type MyReadsBody = components["schemas"]["MyReadsView"];
export type MyArtifactsBody = components["schemas"]["MyArtifactsView"];
export type MyStoredBody = components["schemas"]["MyStoredPage"];

export const MY_DEVICES_API_PATH = "/me/devices";
export const END_MY_DEVICE_API_PATH = "/me/devices/end";
export const MY_READS_API_PATH = "/me/reads";
export const MY_ARTIFACTS_API_PATH = "/me/artifacts";
export const MY_STORED_API_PATH = "/me/stored";

/** The body ending one of a person's own sign-ins sends: its id and nothing else. */
export function endBody(sessionId: string): { readonly session_id: string } {
  return { session_id: sessionId };
}
