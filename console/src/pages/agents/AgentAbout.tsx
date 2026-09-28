/**
 * The About view of one agent: what it is for, how it works, and what it will never do.
 *
 * **Every line is the API's**, from `GET /api/v1/agents/{agent_id}/about`, which
 * `brain.console.agent_about` writes from the agent's setup and nothing else, so the flow cannot
 * describe something the agent is not set up to do. Steps are numbered by the API without a gap, so
 * a step this reader may not see leaves no hole that counts it. This view adds no sentence to the
 * flow; the notes under it say what the page is not sent yet.
 *
 * **Each action line opens its approval setting on the Profile**, at the leash row for that target,
 * or at the leash card when the action has no setting and sits on the Shadow default.
 *
 * **No overview paragraph.** A longer description a person writes needs a manifest path that does
 * not exist yet (`docs/admin-console-architecture.md` 4.1a), and an example paragraph on an install
 * would be text nobody wrote. The view says it is coming.
 *
 * Task ids: M27.10.2, M27.11.16
 */

import { ArrowUpRight, CircleSlash } from "lucide-react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { FailureState, LoadingState, Note } from "../../components/kit";
import { agentAboutApiPath, leashRowId, readAbout } from "./agentDetailQuery";
import { LEASH_ANCHOR } from "./AgentProfile";

export const ABOUT_HEADING = "About this agent";
export const ABOUT_LEDE = "What it is for, how it works, and what it will never do.";
export const SEE_SETUP = "See how it is set up";
export const LOADING_ABOUT = "Loading how this agent works.";
export const NO_SUMMARY = "Nobody has written a summary for this agent yet.";
export const OVERVIEW_SOON =
  "a longer description written by whoever looks after the agent. Today an agent has only its one-line summary.";

function SubHeading({ children }: { readonly children: string }) {
  return <h3 className="m-0 font-mono text-[10.5px] font-medium tracking-[0.1em] text-dim uppercase">{children}</h3>;
}

export function AgentAbout({ agentId, profileAddress }: { readonly agentId: string; readonly profileAddress: string }) {
  const answer = useResource<unknown>(agentAboutApiPath(agentId));
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.busy) {
    return <LoadingState label={LOADING_ABOUT} rows={3} />;
  }
  const about = readAbout(answer.data);
  if (about === null) {
    return null;
  }
  return (
    <section data-slot="agent-about" aria-labelledby="agent-about-heading" className="overflow-hidden rounded-md border border-line bg-panel">
      <div className="flex flex-col gap-2 border-b border-line px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 id="agent-about-heading" className="m-0 text-[16px] font-semibold text-ink">
            {ABOUT_HEADING}
          </h2>
          <p className="m-0 mt-0.5 text-[12.5px] text-dim">{ABOUT_LEDE}</p>
        </div>
        <Link
          to={profileAddress}
          className="inline-flex min-h-11 w-fit shrink-0 items-center gap-1 text-[13px] font-medium text-acc-text underline-offset-4 hover:underline sm:min-h-0"
        >
          {SEE_SETUP} <ArrowUpRight aria-hidden className="size-3.5" />
        </Link>
      </div>

      <div className="flex flex-col gap-3 px-4 py-4">
        <SubHeading>Summary</SubHeading>
        <p className="m-0 text-[15px] leading-relaxed font-medium text-ink [overflow-wrap:anywhere]">{about.summary ?? NO_SUMMARY}</p>
        <Note kind="soon">{OVERVIEW_SOON}</Note>
      </div>

      {about.steps.length === 0 ? null : (
        <div className="flex flex-col gap-3 border-t border-line px-4 py-4">
          <SubHeading>How it works</SubHeading>
          <ol className="m-0 [display:grid] list-none gap-3 p-0 lg:grid-cols-5">
            {about.steps.map((step) => (
              <li key={step.number} className="flex min-w-0 flex-col gap-2 rounded-md border border-line bg-ground p-3">
                <div className="flex items-center gap-2">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-acc-wash font-mono text-[11px] font-semibold text-acc-text">
                    {step.number}
                  </span>
                  <span className="text-[13px] font-semibold text-ink">{step.title}</span>
                </div>
                <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[12.5px] leading-snug text-body">
                  {step.lines.map((line, index) => (
                    <li key={`${String(index)} ${line.text}`} className="[overflow-wrap:anywhere]">
                      {line.tool === undefined ? (
                        line.text
                      ) : (
                        <Link
                          to={`${profileAddress}#${line.leashEntry === true ? leashRowId(line.tool) : LEASH_ANCHOR}`}
                          className="text-body underline decoration-line underline-offset-[3px] hover:text-acc-text"
                        >
                          {line.text}
                        </Link>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
          <Note>Built from how the agent is set up, so it cannot describe anything the agent is not set up to do.</Note>
        </div>
      )}

      {about.never.length === 0 ? null : (
        <div className="flex flex-col gap-3 border-t border-line px-4 py-4">
          <SubHeading>What it will never do</SubHeading>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {about.never.map((one) => (
              <li key={one.text} className="flex items-start gap-2 text-[14px] leading-snug text-ink">
                <CircleSlash aria-hidden className="mt-0.5 size-4 shrink-0 text-crit" />
                <span className="[overflow-wrap:anywhere]">
                  {one.text}
                  {one.everyAgent ? <span className="ml-1.5 font-mono text-[10.5px] text-dim">true of every agent</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
