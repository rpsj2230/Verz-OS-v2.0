/**
 * What the Storage screen asks `brain.storage_routes` for, and how the answer is read. No React.
 *
 * The screen describes the object store's buckets and never their contents: no field on the
 * answer could hold an object's name, and nothing here asks for one. How much a bucket holds is a
 * count the API took on the server, or the API's sentence saying why it was not counted, and a
 * figure the count stopped short of is said as "at least" rather than drawn as a total.
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

const UNITS = ["bytes", "KB", "MB", "GB", "TB"] as const;

/** A byte count in the largest unit that keeps it at or above one, to one decimal place. */
export function bytesInWords(bytes: number): string {
  if (bytes === 1) {
    return "1 byte";
  }
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return unit === 0 ? `${String(bytes)} bytes` : `${value.toFixed(1)} ${UNITS[unit]}`;
}

/**
 * What a bucket holds now, in words: the count, a floor said as a floor, or why it was not counted.
 *
 * Never an empty string and never "0" for a bucket nobody counted: the API sends a sentence in
 * `usage_unread` exactly when there is no count, and that sentence is what is shown.
 */
export function heldNow(bucket: BucketRow): string {
  const usage = bucket.usage;
  if (usage === null || usage === undefined) {
    return bucket.usage_unread ?? "";
  }
  const objects = usage.objects === 1 ? "1 object" : `${String(usage.objects)} objects`;
  const held = `${objects}, ${bytesInWords(usage.bytes_stored)}`;
  return usage.complete ? held : `At least ${held}`;
}
