/**
 * One search box in the header, over every module's own list (M27.10.5).
 *
 * **Everything it shows is what the API's search route sent, and the route is each module's own
 * list asked as the signed-in person.** So this draws groups of hits and links, and decides nothing
 * about who may be told a thing exists. A module the reader may not open and a module with nothing
 * that matches leave no group, so the one sentence for both is "Nothing matches", and there is no
 * count and no "more" anywhere.
 *
 * The header shows a Search button, and the box opens when it is pressed: no input sits on every
 * page for a page's own search to be mistaken for. The query waits a moment after the last key so
 * one word is one request, is at least two characters (the route refuses fewer), and Escape
 * clears and closes the box.
 *
 * Task ids: M27.10.5
 */

import { Search } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";

export const SEARCH_API_PATH = "/console/search";
export const SEARCH_LABEL = "Search the console";
export const NOTHING_MATCHES = "Nothing matches.";
export const MIN_QUERY = 2;
const WAIT_MS = 250;

export interface SearchHit {
  readonly label: string;
  readonly sub?: string;
  readonly to: string;
}

export interface SearchGroup {
  readonly key: string;
  readonly heading: string;
  readonly hits: readonly SearchHit[];
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/** The groups out of a body, dropping any group or hit that is not one. Never a count. */
export function readSearch(payload: unknown): readonly SearchGroup[] {
  const body = typeof payload === "object" && payload !== null ? (payload as { groups?: unknown }) : {};
  const groups: SearchGroup[] = [];
  for (const one of Array.isArray(body.groups) ? (body.groups as unknown[]) : []) {
    const fields = typeof one === "object" && one !== null ? (one as Record<string, unknown>) : {};
    const key = said(fields["key"]);
    const heading = said(fields["heading"]);
    const hits: SearchHit[] = [];
    for (const hit of Array.isArray(fields["hits"]) ? (fields["hits"] as unknown[]) : []) {
      const row = typeof hit === "object" && hit !== null ? (hit as Record<string, unknown>) : {};
      const label = said(row["label"]);
      const to = said(row["to"]);
      const sub = said(row["sub"]);
      if (label !== undefined && to !== undefined && to.startsWith("/")) {
        hits.push({ label, to, ...(sub === undefined ? {} : { sub }) });
      }
    }
    if (key !== undefined && heading !== undefined && hits.length > 0) {
      groups.push({ key, heading, hits });
    }
  }
  return groups;
}

export function searchPath(query: string): string {
  return `${SEARCH_API_PATH}?q=${encodeURIComponent(query)}`;
}

export function GlobalSearch() {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [found, setFound] = useState<readonly SearchGroup[] | null>(null);
  const query = typed.trim();

  useEffect(() => {
    if (query.length < MIN_QUERY) {
      setFound(null);
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      void request<unknown>(searchPath(query)).then((result) => {
        if (live) {
          // A refusal and an answer with nothing in it are one: no group.
          setFound(result.ok ? readSearch(result.data) : []);
        }
      });
    }, WAIT_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query]);

  if (!open) {
    return (
      <button
        type="button"
        data-slot="global-search"
        aria-label={SEARCH_LABEL}
        className="button inline-flex items-center gap-1"
        onClick={() => {
          setOpen(true);
        }}
      >
        <Search aria-hidden className="size-4" />
      </button>
    );
  }
  return (
    <div data-slot="global-search" className="relative min-w-0">
      <input
        autoFocus
        id={id}
        type="search"
        role="searchbox"
        aria-label={SEARCH_LABEL}
        placeholder={SEARCH_LABEL}
        value={typed}
        onChange={(event) => {
          setTyped(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setTyped("");
            setOpen(false);
          }
        }}
        className="h-8 w-48 rounded-md border border-line bg-panel px-2 text-[13px] text-ink md:w-64"
      />
      {found === null ? null : (
        <div
          role="region"
          aria-label="Search results"
          className="absolute right-0 z-20 mt-1 max-h-[70vh] w-80 max-w-[90vw] overflow-auto rounded-md border border-line bg-panel p-2 shadow-md"
        >
          {found.length === 0 ? (
            <p className="m-0 p-1 text-[13px] text-dim">{NOTHING_MATCHES}</p>
          ) : (
            found.map((group) => (
              <section key={group.key} aria-label={group.heading} className="mb-2 last:mb-0">
                <h3 className="m-0 mb-1 text-[11px] font-semibold uppercase tracking-wide text-dim">{group.heading}</h3>
                <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
                  {group.hits.map((hit) => (
                    <li key={`${group.key}${hit.to}`}>
                      <Link
                        to={hit.to}
                        onClick={() => {
                          setTyped("");
                        }}
                        className="flex flex-col rounded px-1.5 py-1 text-[13px] text-ink no-underline hover:bg-sunk"
                      >
                        <span>{hit.label}</span>
                        {hit.sub === undefined ? null : <span className="text-[12px] text-dim">{hit.sub}</span>}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      )}
    </div>
  );
}
