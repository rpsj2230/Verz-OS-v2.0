/**
 * The people who asked, from their own page, for their data to be deleted, listed above the erasure
 * queue for whoever holds the erasure authority (M40.4.2.3).
 *
 * Each is a reference and when they asked, and nothing else: the person is never looked up, for the
 * reason the queue below gives. Nothing here deletes anything. The erasure is filed with the queue's
 * own form, and filing it closes the ask, which the sentence from the API says in its own words.
 * Drawn only for a reader the API told may erase; the API refuses everybody else.
 *
 * Task ids: M40.4.2.3
 */

import { useResource } from "../../api/useResource";
import { Note } from "../../components/kit";
import { WAITING_ASKS_API_PATH, type WaitingAsks } from "../myDeletionQuery";
import { whenWords } from "../review/parts";

export const WAITING_ASKS_CAPTION = "People who asked to be deleted";

export function WaitingAsksList({ version }: { readonly version: number }) {
  const answer = useResource<WaitingAsks>(WAITING_ASKS_API_PATH, version);
  if (answer.data === null || answer.data.requests.length === 0) {
    return null;
  }
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <h3>{WAITING_ASKS_CAPTION}</h3>
      <Note>{answer.data.told}</Note>
      <ul aria-label={WAITING_ASKS_CAPTION}>
        {answer.data.requests.map((one) => (
          <li key={one.request_id}>
            <span className="font-mono text-[12px]">{one.subject_id}</span>
            {` asked ${whenWords(one.requested_at)}`}
          </li>
        ))}
      </ul>
    </div>
  );
}
