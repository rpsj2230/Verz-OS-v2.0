/**
 * The figures for each row the Channels list draws that this release receives on, asked once per
 * row and kept while it is drawn.
 *
 * `agents/useRowStats.ts`' shape and its reasons: one request per row asked by the page rather than
 * by each cell, a failure kept per row and drawn as "Not available", and nothing drawn as nought.
 * Only a channel the release receives on is asked about, because the stats route answers only
 * those, and a request the page knows will be refused is a request whose refusal says nothing.
 *
 * Task ids: M27.13.1, M27.16.1
 */

import { useEffect, useRef, useState } from "react";
import { request } from "../../api/client";
import { channelStatsApiPath, readChannelStats, type ChannelStats } from "./channelStats";

export type RowFigures =
  | { readonly kind: "loading" }
  | { readonly kind: "failed" }
  | { readonly kind: "ready"; readonly stats: ChannelStats };

const LOADING: RowFigures = Object.freeze({ kind: "loading" });

export function useChannelStats(names: readonly string[]): (name: string) => RowFigures {
  const [answers, setAnswers] = useState<ReadonlyMap<string, RowFigures>>(new Map());
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
        const result = await request<unknown>(channelStatsApiPath(name));
        if (!mounted.current) {
          return;
        }
        const read = result.ok ? readChannelStats(result.data) : null;
        const settled: RowFigures = read === null ? { kind: "failed" } : { kind: "ready", stats: read };
        setAnswers((before) => new Map(before).set(name, settled));
      })();
    }
  }, [key]);

  return (name: string) => answers.get(name) ?? LOADING;
}
