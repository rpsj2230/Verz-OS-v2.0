/**
 * One long list, asked of the API a page at a time, with its search, filters and order.
 *
 * **Pages are appended, not replaced.** "Show more" asks for the page after the last one drawn and
 * adds its rows under them, which is `Audit.tsx`' arrangement. It keeps what a reader ticked on
 * earlier rows in view for a bulk act, and it needs no back stack: a changed question starts again
 * from the first page, because a cursor is a position in one question's walk and the server refuses
 * one carried across to another.
 *
 * **The body a page reads is the first page's, with its list replaced by every row drawn so far.**
 * So a page's own reader (`readSessionsPage` and its siblings) is unchanged: the sentences the API
 * serves arrive on the first page, and the list is what the reader has walked.
 *
 * **A superseded answer never overwrites a newer one.** Typing in the search box asks once per
 * keystroke and the answers do not come back in order, so each request carries a sequence number and
 * only the current one may set state, which is `useServerPage.ts`' rule and its reason.
 *
 * **Asking again is a version the caller moves**, for `useResource.ts`' reason: a page that has just
 * written something asks for the first page again without being rebuilt, and keeps the question.
 *
 * Task ids: M27.8.6
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import {
  LIST_PAGE_SIZE,
  NO_QUESTION,
  listPath,
  offeredFrom,
  type FilterChoice,
  type ListQuestion,
} from "./listing";

export interface ListingOptions<Row> {
  /** The key the route's rows travel under. `items` unless the route says otherwise. */
  readonly listKey?: string;
  readonly pageSize?: number;
  /** The filters the page offers, whose values are gathered from the rows drawn. */
  readonly choices?: readonly FilterChoice<Row>[];
  /** Parameters of the route's own, such as a period, sent with every page. */
  readonly extra?: Readonly<Record<string, string>>;
  /** Moved by the caller after a write, to ask for the first page again. */
  readonly version?: number;
  readonly initial?: ListQuestion;
}

export interface Listing<Row> {
  /** The first page's body with its list replaced by every row drawn, or null before an answer. */
  readonly body: unknown;
  /** Every row drawn so far, in the order the pages came. */
  readonly rows: readonly Row[];
  /** Why the first page did not come, in the API's words, or null. */
  readonly failure: ApiFailure | null;
  /** The first page of the current question is in flight. */
  readonly busy: boolean;
  /** The API sent a cursor for a page after the last one drawn. */
  readonly more: boolean;
  readonly fetchingMore: boolean;
  /** Why the last "Show more" did not come, or null. The rows drawn stay drawn. */
  readonly moreFailure: ApiFailure | null;
  readonly showMore: () => void;
  readonly question: ListQuestion;
  readonly ask: (question: ListQuestion) => void;
  /** The values each filter may offer: only values carried by rows drawn. */
  readonly offered: Readonly<Record<string, readonly string[]>>;
}

interface Walk<Row> {
  readonly body: Record<string, unknown> | null;
  readonly rows: readonly Row[];
  readonly cursor: string | null;
}

const NOWHERE: Walk<never> = Object.freeze({ body: null, rows: [], cursor: null });

function rowsIn<Row>(body: unknown, listKey: string): readonly Row[] {
  if (typeof body !== "object" || body === null) {
    return [];
  }
  const found = (body as Record<string, unknown>)[listKey];
  return Array.isArray(found) ? (found as Row[]) : [];
}

function cursorIn(body: unknown): string | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const found = (body as { next_cursor?: unknown }).next_cursor;
  return typeof found === "string" && found !== "" ? found : null;
}

export function useListing<Row>(path: string, options: ListingOptions<Row> = {}): Listing<Row> {
  const listKey = options.listKey ?? "items";
  const pageSize = options.pageSize ?? LIST_PAGE_SIZE;
  const version = options.version ?? 0;
  const extraKey = JSON.stringify(options.extra ?? {});
  const [question, setQuestion] = useState<ListQuestion>(options.initial ?? NO_QUESTION);
  const [walk, setWalk] = useState<Walk<Row>>(NOWHERE);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(true);
  const [fetchingMore, setFetchingMore] = useState(false);
  const [moreFailure, setMoreFailure] = useState<ApiFailure | null>(null);
  const [offered, setOffered] = useState<Readonly<Record<string, readonly string[]>>>({});
  const sequence = useRef(0);
  const choices = useRef(options.choices ?? []);
  choices.current = options.choices ?? [];

  useEffect(() => {
    sequence.current += 1;
    const mine = sequence.current;
    const controller = new AbortController();
    const extra = JSON.parse(extraKey) as Record<string, string>;
    setBusy(true);
    setFailure(null);
    setMoreFailure(null);

    void (async () => {
      const result = await request<unknown>(listPath(path, question, null, pageSize, extra), {
        signal: controller.signal,
      });
      if (mine !== sequence.current) {
        return;
      }
      if (!result.ok) {
        setWalk(NOWHERE);
        setFailure(result.failure);
        setBusy(false);
        return;
      }
      const rows = rowsIn<Row>(result.data, listKey);
      const body =
        typeof result.data === "object" && result.data !== null
          ? (result.data as Record<string, unknown>)
          : null;
      setWalk({ body, rows, cursor: cursorIn(result.data) });
      setOffered((previous) => offeredFrom(previous, rows, choices.current));
      setBusy(false);
    })();

    return () => {
      controller.abort();
    };
  }, [path, question, pageSize, extraKey, listKey, version]);

  const showMore = useCallback(() => {
    const cursor = walk.cursor;
    if (cursor === null || fetchingMore) {
      return;
    }
    const mine = sequence.current;
    const extra = JSON.parse(extraKey) as Record<string, string>;
    setFetchingMore(true);
    setMoreFailure(null);
    void (async () => {
      const result = await request<unknown>(listPath(path, question, cursor, pageSize, extra));
      if (mine !== sequence.current) {
        return;
      }
      setFetchingMore(false);
      if (!result.ok) {
        setMoreFailure(result.failure);
        return;
      }
      const rows = rowsIn<Row>(result.data, listKey);
      setWalk((current) => ({
        body: current.body,
        rows: [...current.rows, ...rows],
        cursor: cursorIn(result.data),
      }));
      setOffered((previous) => offeredFrom(previous, rows, choices.current));
    })();
  }, [walk.cursor, fetchingMore, path, question, pageSize, extraKey, listKey]);

  const ask = useCallback((next: ListQuestion) => {
    setQuestion(next);
  }, []);

  // A body that carried no list under its key is handed back untouched, so a page's own reader still
  // says it is not a page rather than reading an empty list this hook put there.
  const body =
    walk.body === null || !Array.isArray(walk.body[listKey])
      ? walk.body
      : { ...walk.body, [listKey]: walk.rows, next_cursor: walk.cursor };

  return {
    body,
    rows: walk.rows,
    failure,
    busy,
    more: walk.cursor !== null,
    fetchingMore,
    moreFailure,
    showMore,
    question,
    ask,
    offered,
  };
}
