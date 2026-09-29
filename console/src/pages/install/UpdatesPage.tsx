/**
 * Version and updates on the shared page kit: which release is running, whether a newer one has
 * been published, and what has been deployed here.
 *
 * **The standing is the API's word and the two sentences under it are the API's sentences.**
 * `brain.console.version_view.ANSWERS` is total over its answers, written for somebody with a
 * server and no source tree; a console sentence per word would be a second vocabulary for a closed
 * set. **Nothing here is a tick or a colour** (`installQuery.ts`' third rule).
 *
 * **What is running is a release when there is one, with the commit beside it under its own
 * label.** When no release is named the API's reason stands where the release would be.
 *
 * **Nothing waits for the release list.** The API answers from the last finished look, so the first
 * load after a start may say no look has finished. That is drawn in the "newest release" card from
 * the API's `look` sentence: until 2026-09-29 it was drawn only under the standing, and an install
 * running `:latest` has a standing about its running release instead, so on the owner's install
 * the check was switched on and the page said nothing about it at all.
 *
 * **What was removed**: the lede about asking outside the network (the release check is now a
 * Features switch that says so where it is turned on) and the instruction drawn twice.
 *
 * Task ids: M27.7.25, M42.3.9, M38.1.3.5, M27.15.51, M27.16.1
 */

import { useResource } from "../../api/useResource";
import { Chip, Fact, FailureState, LoadingState, Note, PageHeader, SectionCard } from "../../components/kit";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { UPDATES_API_PATH, type Updates as UpdatesPanel } from "../installQuery";
import { InstallFacts } from "./InstallFacts";

export const UPDATES_HEADING = "Version and updates";
export const UPDATES_LEDE = "Which release is running here, and whether a newer one has been published.";
export const READING_UPDATES = "Reading which release is running.";
export const NO_RELEASE_NAMED = "This install does not name a release";
export const READ_ITS_NOTES = "Read its release notes";
export const DEPLOYED_HERE = "What has been deployed here";
export const DEPLOYS_CAPTION = "Deploys on this install, newest first";
export const HISTORY_CHANGED = "This history was changed after it was written";
export const NEWEST_RELEASE = "The newest published release";

function Panel({ panel }: { readonly panel: UpdatesPanel }) {
  const { running, told, unanswered, history } = panel;
  return (
    <>
      <SectionCard title="Where this install stands" action={<Chip>{panel.standing}</Chip>}>
        <p className="m-0 text-[13px] text-body">{panel.says}</p>
        {panel.what_to_do ? <p className="m-0 mt-2 text-[12.5px] text-dim">{panel.what_to_do}</p> : null}
      </SectionCard>

      <SectionCard title="What is running">
        <dl data-slot="fact-list" aria-label="The version running here" className="m-0 mb-3 flex min-w-0 flex-col">
          <Fact label="Release">
            {running.tag ? (
              <span className="font-mono text-[12.5px]">{running.tag}</span>
            ) : (
              <>
                <span>{NO_RELEASE_NAMED}</span>
                <p className="m-0 mt-1 text-[12px] text-dim">{running.cannot_say}</p>
              </>
            )}
          </Fact>
          {running.commit ? (
            <Fact label="Commit">
              <span className="font-mono text-[12.5px]">{running.commit}</span>
            </Fact>
          ) : null}
        </dl>
        <InstallFacts facts={running.facts} label="Where a version could be read from" />
      </SectionCard>

      {told ? (
        <SectionCard title={NEWEST_RELEASE}>
          <dl data-slot="fact-list" aria-label={NEWEST_RELEASE} className="m-0 flex min-w-0 flex-col">
            <Fact label="Newest release">{told.tag}</Fact>
            {told.notes ? (
              <Fact label="Notes">
                <a href={told.notes} rel="noreferrer" className="text-acc-text underline underline-offset-4">
                  {READ_ITS_NOTES}
                </a>
              </Fact>
            ) : null}
            <Fact label="Said by">{told.by}</Fact>
            <Fact label="Said at">{told.at}</Fact>
          </dl>
        </SectionCard>
      ) : null}
      {!told && unanswered ? (
        <SectionCard title={NEWEST_RELEASE} action={<Chip>{unanswered.why}</Chip>}>
          <p className="m-0 text-[12.5px] text-dim">{unanswered.detail}</p>
        </SectionCard>
      ) : null}
      {!told && !unanswered && panel.look ? (
        <SectionCard title={NEWEST_RELEASE}>
          <p className="m-0 text-[12.5px] text-dim">{panel.look}</p>
        </SectionCard>
      ) : null}

      {history ? (
        <SectionCard title={DEPLOYED_HERE} lede={history.deploys ? history.says : undefined}>
          {history.deploys ? (
            <>
              {history.holds ? null : (
                <div role="alert" className="mb-2">
                  <Note kind="not-yet">{HISTORY_CHANGED}</Note>
                </div>
              )}
              {history.deploys.length ? (
                <Table aria-label={DEPLOYS_CAPTION}>
                  <TableCaption className="sr-only">{DEPLOYS_CAPTION}</TableCaption>
                  <TableHeader>
                    <TableRow>
                      <TableHead>When</TableHead>
                      <TableHead>Commit</TableHead>
                      <TableHead>Outcome</TableHead>
                      <TableHead>Tasks in this release</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {history.deploys.map((deploy) => (
                      <TableRow key={deploy.seq}>
                        <TableCell className="font-mono text-[12px]">{deploy.at}</TableCell>
                        <TableCell className="font-mono text-[12px]">{deploy.commit}</TableCell>
                        <TableCell>
                          <Chip>{deploy.outcome}</Chip>
                        </TableCell>
                        <TableCell className="whitespace-normal font-mono text-[12px] [overflow-wrap:anywhere]">
                          {deploy.task_ids.join(", ")}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : null}
            </>
          ) : (
            <p className="m-0 text-[12.5px] text-dim">{history.unread}</p>
          )}
        </SectionCard>
      ) : null}
    </>
  );
}

export function UpdatesPage() {
  const answer = useResource<UpdatesPanel>(UPDATES_API_PATH);
  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_UPDATES} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.data) {
    content = <Panel panel={answer.data} />;
  } else {
    content = null;
  }
  return (
    <div data-slot="updates-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: UPDATES_HEADING }]} title={UPDATES_HEADING} lede={UPDATES_LEDE} />
      {content}
    </div>
  );
}
