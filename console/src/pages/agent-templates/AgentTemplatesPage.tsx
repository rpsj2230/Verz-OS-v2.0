/**
 * The template catalogue on the shared page kit: every role an agent can be installed from, what
 * ships with the product and what this install has published, each with its own page.
 *
 * **Nothing here decides who may read it.** The route answers behind the Skills and templates
 * screen's read and refuses everybody else in that screen's words, drawn as any refusal is.
 *
 * **No install count and no department**, for `agentTemplatesQuery.ts`' reason: the agents made
 * from a template are agents, and a count of them is a count of rows this reader may not see.
 *
 * **What was removed**: the static "What a template carries" table (a fact about the manifest
 * type, now said by each template's own page in its own values), the published-by column (a
 * principal id, on the template's page in Advanced), and the paragraph saying installing was not
 * offered, which is no longer true for a published version.
 *
 * Task ids: M27.8.6, M27.11.7, M27.16.1
 */

import { LayoutTemplate, Plus } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import type { FilterChoice, SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { Chip, ListPage, UnavailableAction, type EntityColumn } from "../../components/kit";
import { readTemplates, TEMPLATES_API_PATH, type TemplateCard } from "../agentTemplatesQuery";
import { ACT_LABELS, originWords, UNAVAILABLE } from "./templateActions";

export const TEMPLATES_HEADING = "Agent templates";
export const TEMPLATES_LEDE =
  "Roles an agent can be installed from. Installing never widens anyone: a run is still bounded by whoever called it.";
export const READING_TEMPLATES = "Reading the template catalogue.";
export const NO_TEMPLATES = "No templates to show";
export const NO_TEMPLATES_DESCRIPTION = "A template appears here once the product ships one or this install publishes one.";
export const TEMPLATES_LIST_LABEL = "Templates you can install from";
export const FILTERS_LABEL = "Narrow the templates";
export const SEARCH_HINT = "Search templates";

export function templateAddress(templateId: string): string {
  return `/agent-templates/${encodeURIComponent(templateId)}`;
}

export const TEMPLATE_FILTERS: readonly FilterChoice<TemplateCard>[] = [
  { column: "origin", label: "Where from", everything: "Anywhere", read: (row) => row.origin, describe: originWords },
];

export const TEMPLATE_SORTS: readonly SortChoice[] = [
  { value: "", label: "Name" },
  { value: "-version", label: "Newest version" },
  { value: "origin", label: "Where from" },
];

export function AgentTemplatesPage() {
  const listing = useListing<TemplateCard>(TEMPLATES_API_PATH, { choices: TEMPLATE_FILTERS });
  const rows = useMemo(() => readTemplates(listing.body)?.cards ?? [], [listing.body]);

  const columns: readonly EntityColumn<TemplateCard>[] = [
    {
      id: "name",
      header: "Template",
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[14rem] flex-col">
          <Link to={templateAddress(row.templateId)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
            {row.displayName}
          </Link>
          {row.summary === undefined ? null : <span className="text-[12px] text-dim">{row.summary}</span>}
        </span>
      ),
      text: (row) => row.displayName,
    },
    {
      id: "version",
      header: "Version",
      align: "end",
      cell: (row) => <span className="font-mono text-[12px] tabular-nums">{String(row.version)}</span>,
      text: (row) => String(row.version),
    },
    {
      id: "origin",
      header: "Where from",
      cell: (row) => <Chip>{originWords(row.origin)}</Chip>,
      text: (row) => originWords(row.origin),
    },
  ];

  return (
    <ListPage
      crumbs={[{ label: TEMPLATES_HEADING }]}
      title={TEMPLATES_HEADING}
      lede={TEMPLATES_LEDE}
      primary={<UnavailableAction label={ACT_LABELS.author} text={ACT_LABELS.author} icon={<Plus aria-hidden />} reason={UNAVAILABLE.author.reason} />}
      listing={listing}
      rows={rows}
      filtersLabel={FILTERS_LABEL}
      choices={TEMPLATE_FILTERS}
      sorts={TEMPLATE_SORTS}
      searchHint={SEARCH_HINT}
      caption={TEMPLATES_LIST_LABEL}
      columns={columns}
      rowId={(row) => row.templateId}
      rowLabel={(row) => row.displayName}
      exportName="agent-templates"
      loading={READING_TEMPLATES}
      emptyTitle={NO_TEMPLATES}
      emptyDescription={NO_TEMPLATES_DESCRIPTION}
      emptyIcon={<LayoutTemplate aria-hidden />}
    />
  );
}
