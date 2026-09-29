/**
 * One question asked of the ledger, a page at a time: the first page, "Show older entries", and
 * what happened to each.
 *
 * **Not `useListing`, because the ledger is not the list contract.** `GET /audit` takes its own
 * filters (an action, a kind, an actor, a window and an order) rather than `filter=column:value`,
 * so the pages keep the shape `Audit.tsx` had: the first page is asked when the question changes,
 * later pages are appended from the cursor, and a changed question starts again because a cursor is
 * a position in one question's walk.
 *
 * **The window is measured from one instant per question**, fixed when the question is, so fetching
 * more does not move the period under the pages already drawn.
 *
 * Task ids: M27.7.13, M27.8.6, M27.16.1
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { auditApiPath, readLedgerPage, type AuditFilters, type AuditRow, type LedgerPage } from "../auditQuery";

export interface Ledger {
  readonly first: LedgerPage | null;
  readonly rows: readonly AuditRow[];
  /** Every name the pages drawn so far carried. */
  readonly people: Readonly<Record<string, string>>;
  readonly failure: ApiFailure | null;
  readonly busy: boolean;
  readonly more: boolean;
  readonly fetchingMore: boolean;
  readonly moreFailure: ApiFailure | null;
  readonly showMore: () => void;
}

export function useLedger(
  filters: AuditFilters,
  subject: { readonly kind: string; readonly id: string } | null = null,
): Ledger {
  const key = JSON.stringify([filters, subject]);
  const [pages, setPages] = useState<readonly LedgerPage[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(true);
  const [fetchingMore, setFetchingMore] = useState(false);
  const [moreFailure, setMoreFailure] = useState<ApiFailure | null>(null);
  const sequence = useRef(0);
  // The question and the instant its period is measured from, fixed together.
  const asked = useMemo(() => {
    const [chosen, about] = JSON.parse(key) as [AuditFilters, { kind: string; id: string } | null];
    return { chosen, about, now: new Date() };
  }, [key]);

  useEffect(() => {
    sequence.current += 1;
    const mine = sequence.current;
    setBusy(true);
    setFailure(null);
    setMoreFailure(null);
    setPages([]);
    void (async () => {
      const result = await request<unknown>(auditApiPath(asked.chosen, asked.now, null, asked.about));
      if (mine !== sequence.current) {
        return;
      }
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setPages([readLedgerPage(result.data)]);
    })();
  }, [asked]);

  const last = pages[pages.length - 1] ?? null;
  const cursor = last?.nextCursor ?? null;
  const showMore = useCallback(() => {
    if (cursor === null) {
      return;
    }
    const mine = sequence.current;
    setFetchingMore(true);
    void (async () => {
      const result = await request<unknown>(auditApiPath(asked.chosen, asked.now, cursor, asked.about));
      if (mine !== sequence.current) {
        return;
      }
      setFetchingMore(false);
      if (!result.ok) {
        setMoreFailure(result.failure);
        return;
      }
      setMoreFailure(null);
      setPages((earlier) => [...earlier, readLedgerPage(result.data)]);
    })();
  }, [asked, cursor]);

  const rows = useMemo(() => pages.flatMap((one) => one.rows), [pages]);
  const people = useMemo(() => Object.assign({}, ...pages.map((one) => one.people)) as Record<string, string>, [pages]);
  return {
    first: pages[0] ?? null,
    rows,
    people,
    failure,
    busy,
    more: cursor !== null,
    fetchingMore,
    moreFailure,
    showMore,
  };
}
