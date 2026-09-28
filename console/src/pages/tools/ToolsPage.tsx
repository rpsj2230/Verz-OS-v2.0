/**
 * Tools on the shared page kit: every tool an agent, a workflow or an automation can call on this
 * install, whether it is on, and a page per tool with its switch.
 *
 * **The route answers the whole registry at once and takes no search, filter or order**, so the
 * list is the kit's table without the toolbar: a search box over a route that ignores it would look
 * like a narrowed list and be the whole one.
 *
 * **What was removed**: a card per tool with six facts and its switches all on one page (each tool
 * has its page now), who switched a tool off (a principal id, now in the tool page's Advanced), and
 * the three-paragraph "what a switch does" card, which is one sentence under the list.
 *
 * Task ids: M12.1.1, M12.1.3, M12.1.4, M12.3.8, M12.4.3, M27.16.1
 */

import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Chip, EntityTable, FailureState, LoadingState, Note, PageHeader, SectionCard, EmptyState, type EntityColumn } from "../../components/kit";
import {
  A_SWITCH_ONLY_NARROWS,
  EFFECT_WORDS,
  NO_TOOLS,
  READING_TOOLS,
  readTools,
  RUNG_WORDS,
  TOOLS_API_PATH,
  TOOLS_LABEL,
  TOOLS_LEDE,
  UNREADABLE_ANSWER,
  type ToolRow,
} from "../toolsQuery";

export const TOOLS_LIST_LABEL = "Tools on this install";
export const NO_TOOLS_DESCRIPTION = "A tool appears here once a connector or a skill that registers one is installed.";

export function toolAddress(name: string): string {
  return `/tools/${encodeURIComponent(name)}`;
}

/** Where a tool is switched off, as the short words a status column holds. */
export function statusWords(row: ToolRow): string[] {
  const words: string[] = [];
  if (!row.registered) {
    words.push("No longer offered");
  }
  if (row.off_for_install !== null && row.off_for_install !== undefined) {
    words.push("Off for the install");
  }
  for (const stop of row.stopped_for) {
    words.push(`Stopped for ${stop.department ?? ""}`);
  }
  return words.length === 0 ? ["On"] : words;
}

export function StatusChips({ row }: { readonly row: ToolRow }) {
  return (
    <span className="flex flex-wrap gap-1">
      {statusWords(row).map((word) => (
        <Chip key={word}>
          {word}
        </Chip>
      ))}
    </span>
  );
}

export function ToolsPage() {
  const answer = useResource<unknown>(TOOLS_API_PATH);
  const columns: readonly EntityColumn<ToolRow>[] = [
    {
      id: "name",
      header: "Tool",
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[14rem] flex-col">
          <Link to={toolAddress(row.name)} className="font-mono text-[12.5px] font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
            {row.name}
          </Link>
          <span className="text-[12px] text-dim">{row.description}</span>
        </span>
      ),
      text: (row) => row.name,
    },
    { id: "source", header: "Source", cell: (row) => row.source, text: (row) => row.source },
    { id: "effect", header: "Effect", cell: (row) => EFFECT_WORDS[row.effect] ?? row.effect, text: (row) => EFFECT_WORDS[row.effect] ?? row.effect },
    { id: "status", header: "Status", cell: (row) => <StatusChips row={row} />, text: (row) => statusWords(row).join("; ") },
    {
      id: "leash",
      header: "Leash at most",
      hidden: true,
      cell: (row) => RUNG_WORDS[row.leash_at_most] ?? row.leash_at_most,
      text: (row) => RUNG_WORDS[row.leash_at_most] ?? row.leash_at_most,
    },
  ];

  let body;
  if (answer.busy) {
    body = <LoadingState label={READING_TOOLS} />;
  } else if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else {
    const page = readTools(answer.data);
    if (page === null) {
      body = <Note>{UNREADABLE_ANSWER}</Note>;
    } else if (page.tools.length === 0) {
      body = <EmptyState title={NO_TOOLS} description={NO_TOOLS_DESCRIPTION} />;
    } else {
      body = (
        <EntityTable
          caption={TOOLS_LIST_LABEL}
          columns={columns}
          rows={page.tools}
          rowId={(row) => row.name}
          rowLabel={(row) => row.name}
          exportName="tools"
        />
      );
    }
  }

  return (
    <div data-slot="list-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: TOOLS_LABEL }]} title={TOOLS_LABEL} lede={TOOLS_LEDE} />
      <SectionCard title={TOOLS_LIST_LABEL} footer={<Note>{A_SWITCH_ONLY_NARROWS}</Note>}>
        {body}
      </SectionCard>
    </div>
  );
}
