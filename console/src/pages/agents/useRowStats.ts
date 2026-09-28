/**
 * The figures for each row a list draws, asked once per row and kept while the rows stay drawn.
 *
 * **One request per row, asked by the page and not by each cell.** Two columns read the same
 * figures (last run and runs), and a cell that fetched for itself would ask twice and render the two
 * halves of one row from two answers that may disagree. So the page asks once per row id it has not
 * asked about yet, and the cells read the answer.
 *
 * **A row's figures that fail are that row's, and say so.** A failure is kept per row and drawn as
 * "Not available" in its cells, so one agent whose figures cannot be read does not take the list
 * down, and nothing is drawn as nought.
 *
 * Rejected: one request for the whole page's figures. It would be cheaper, and no such route exists;
 * the stats package serves one entity at a time. If a list route ever carries the figures, this hook
 * goes and the cells read the row.
 *
 * Task ids: M27.10.2
 */

import { useEffect, useRef, useState } from "react";
import { request } from "../../api/client";
import { readAgentStats, agentStatsApiPath, type AgentStats } from "./agentStats";

export type RowStats =
  | { readonly kind: "loading" }
  | { readonly kind: "failed" }
  | { readonly kind: "ready"; readonly stats: AgentStats };

const LOADING: RowStats = Object.freeze({ kind: "loading" });

export function useRowStats(ids: readonly string[]): (id: string) => RowStats {
  const [answers, setAnswers] = useState<ReadonlyMap<string, RowStats>>(new Map());
  const asked = useRef(new Set<string>());
  const mounted = useRef(true);
  const key = ids.join("\u0000");

  useEffect(() => {
    mounted.current = true;
    return () => {
      // An answer that arrives after the page has gone is dropped rather than set on nothing.
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const fresh = key === "" ? [] : key.split("\u0000").filter((id) => !asked.current.has(id));
    for (const id of fresh) {
      // Asked once for as long as the page is drawn: "Show more" adds rows and asks only for those.
      asked.current.add(id);
      void (async () => {
        const result = await request<unknown>(agentStatsApiPath(id));
        if (!mounted.current) {
          return;
        }
        const read = result.ok ? readAgentStats(result.data) : null;
        const settled: RowStats = read === null ? { kind: "failed" } : { kind: "ready", stats: read };
        setAnswers((before) => new Map(before).set(id, settled));
      })();
    }
  }, [key]);

  return (id: string) => answers.get(id) ?? LOADING;
}
