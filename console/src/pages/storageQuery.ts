/**
 * What the Storage screen asks `brain.storage_routes` for, and how the answer is read. No React.
 *
 * The screen describes the object store's buckets and never their contents: no field on the
 * answer could hold an object's name, and nothing here asks for one. Usage is not drawn as a bar,
 * because nothing measures it, and the API's sentence saying so is shown where a bar would be.
 *
 * Task ids: M27.8.15
 */

import type { components } from "../api/schema";

export type StorageBody = components["schemas"]["StorageView"];
export type BucketRow = components["schemas"]["BucketView"];

/** Where the API keeps the screen. */
export const STORAGE_API_PATH = "/storage";

/** The console address and the menu's label. */
export const STORAGE_PATH = "/storage";
export const STORAGE_LABEL = "Storage";

/** Read `StorageView` out of a response body, or null when it is not one. */
export function readStorage(payload: unknown): StorageBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { buckets?: unknown; endpoint?: unknown; findings?: unknown };
  if (!Array.isArray(body.buckets) || !Array.isArray(body.findings) || !body.endpoint) {
    return null;
  }
  return payload as StorageBody;
}

/** How long a bucket keeps what it holds, in words. None means kept until deleted. */
export function keptFor(bucket: BucketRow): string {
  if (bucket.retention_days === null) {
    return "Until deleted";
  }
  return bucket.retention_days === 1 ? "1 day" : `${String(bucket.retention_days)} days`;
}
