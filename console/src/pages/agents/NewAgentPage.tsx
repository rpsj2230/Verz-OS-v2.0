/**
 * New agent: start a draft from scratch or from a template, as Part 4.1 of the console's design
 * draws the flow. What follows (write, draw a procedure, check, rehearse, publish) is the draft's
 * own page.
 *
 * **Two ways in, each a confirmed act.** From scratch is the blank template, whose sealed values
 * are the strictest there are; from a template is that template's words copied into a draft of the
 * reader's own, to be changed before anything is published. Neither makes an agent: a draft is a
 * draft until it is checked and published, which the confirmation says before anything is sent.
 *
 * **The templates are the gallery's**, read from `GET /api/v1/agent-templates` behind the gallery's
 * own grant. A reader who cannot open the gallery is shown the API's refusal in that card and can
 * still start from scratch.
 *
 * Task ids: M27.11.6, M27.16.1
 */

import { FilePlus2, LayoutTemplate } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { FailureState, LoadingState, Note, PageHeader, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { WORKS_AT } from "./agentActions";
import { ROSTER_HEADING } from "./AgentsPage";
import {
  DRAFTS_ADDRESS,
  NOTHING_IS_LIVE,
  TEMPLATES_API_PATH,
  readTemplates,
} from "./agentDraftsQuery";
import { useDraftStart } from "./DraftStart";

export const NEW_AGENT_HEADING = "New agent";
export const NEW_AGENT_LEDE =
  "Start a draft. You write it, check it, rehearse it and publish it; nothing is live until then.";
export const SCRATCH_HEADING = "From scratch";
export const SCRATCH_LEDE = "An empty agent that reaches nothing and acts on nothing until you give it permissions.";
export const SCRATCH_LABEL = "Start from scratch";
export const TEMPLATE_HEADING = "From a template";
export const TEMPLATE_LEDE = "A copy of a template's words and settings, yours to change before it is published.";
export const FROM_THIS = "Start from this";
export const LOADING_TEMPLATES = "Loading templates.";
export const NO_TEMPLATES = "No template is offered on this install yet.";
export const YOUR_DRAFTS = "Your drafts";
export const ALL_TEMPLATES = "All templates";

export function NewAgentPage() {
  const start = useDraftStart();
  const gallery = useResource<unknown>(TEMPLATES_API_PATH);
  const templates = useMemo(() => readTemplates(gallery.data), [gallery.data]);

  return (
    <div data-slot="new-agent-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: ROSTER_HEADING, to: "/agents" }, { label: NEW_AGENT_HEADING }]}
        title={NEW_AGENT_HEADING}
        lede={NEW_AGENT_LEDE}
        actions={
          <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
            <Link to={DRAFTS_ADDRESS}>{YOUR_DRAFTS}</Link>
          </Button>
        }
      />
      {start.notice}
      {start.dialog}
      <Note>{NOTHING_IS_LIVE}</Note>
      <div className="[display:grid] min-w-0 gap-4 lg:grid-cols-2">
        <SectionCard
          title={SCRATCH_HEADING}
          lede={SCRATCH_LEDE}
          action={<FilePlus2 aria-hidden className="size-4 text-dim" />}
        >
          <Button
            className="min-h-11 w-fit sm:min-h-9"
            disabled={start.busy}
            onClick={() => {
              start.begin({ kind: "scratch" });
            }}
          >
            {SCRATCH_LABEL}
          </Button>
        </SectionCard>
        <SectionCard
          title={TEMPLATE_HEADING}
          lede={TEMPLATE_LEDE}
          action={
            <Link to={WORKS_AT.templates} className="inline-flex min-h-11 items-center gap-1 text-[12.5px] text-acc-text underline-offset-4 hover:underline sm:min-h-8">
              <LayoutTemplate aria-hidden className="size-4" />
              {ALL_TEMPLATES}
            </Link>
          }
        >
          {gallery.failure !== null ? (
            <FailureState failure={gallery.failure} />
          ) : gallery.busy ? (
            <LoadingState label={LOADING_TEMPLATES} rows={3} />
          ) : templates.length === 0 ? (
            <p className="m-0 text-sm text-dim">{NO_TEMPLATES}</p>
          ) : (
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {templates.map((one) => (
                <li
                  key={one.templateId}
                  className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-md border border-line p-3"
                >
                  <span className="flex min-w-0 flex-col">
                    <span className="font-medium text-ink [overflow-wrap:anywhere]">{one.name}</span>
                    {one.summary === undefined ? null : (
                      <span className="text-[12.5px] text-dim [overflow-wrap:anywhere]">{one.summary}</span>
                    )}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    className="min-h-11 sm:min-h-8"
                    aria-label={`${FROM_THIS}: ${one.name}`}
                    disabled={start.busy}
                    onClick={() => {
                      start.begin({ kind: "template", templateId: one.templateId, name: one.name });
                    }}
                  >
                    {FROM_THIS}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
