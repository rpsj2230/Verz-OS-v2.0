/**
 * The figures for each connected row the list draws, asked once per row and kept while it is drawn.
 *
 * `agents/useRowStats.ts`' shape and its reasons, over the connectors' own stats route: one request
 * per row asked by the page rather than by each cell, a failure kept per row and drawn as "Not
 * available", and nothing drawn as nought. Only a connected row is asked about: a source nobody
 * connected, or one this reader may not be told is connected, has no figures, and asking for them
 * would be a request whose refusal the page could tell apart.
 *
 * Task ids: M27.11.9
 */

import { useEffect, useRef, useState } from "react";
import { request } from "../../api/client";
import { connectorStatsApiPath, readConnectorStats, type ConnectorStats } from "./connectorStats";

export type SourceStats =
  | { readonly kind: "loading" }
  | { readonly kind: "failed" }
  | { readonly kind: "ready"; readonly stats: ConnectorStats };

const LOADING: SourceStats = Object.freeze({ kind: "loading" });

export function useSourceStats(names: readonly string[]): (name: string) => SourceStats {
  const [answers, setAnswers] = useState<ReadonlyMap<string, SourceStats>>(new Map());
  const asked = useRef(new Set<string>());
  const mounted = useRef(true);
  const key = names.join("\u0000");

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const fresh = key === "" ? [] : key.split("\u0000").filter((name) => !asked.current.has(name));
    for (const name of fresh) {
      asked.current.add(name);
      void (async () => {
        const result = await request<unknown>(connectorStatsApiPath(name));
        if (!mounted.current) {
          return;
        }
        const read = result.ok ? readConnectorStats(result.data) : null;
        const settled: SourceStats = read === null ? { kind: "failed" } : { kind: "ready", stats: read };
        setAnswers((before) => new Map(before).set(name, settled));
      })();
    }
  }, [key]);

  return (name: string) => answers.get(name) ?? LOADING;
}
