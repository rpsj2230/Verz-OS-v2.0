/**
 * This install on the shared page kit: what is actually running, each fact labelled with how firmly
 * it is known.
 *
 * **This page adds no interpretation to any value**, which is `installQuery.ts`' first rule: the
 * release is `unknown` outside a built image and the migration level `declared`, each with the API's
 * sentence, and a summary into "healthy" would compose a verdict out of three kinds of statement.
 * No refresh control and no timestamp: the facts do not move without a deploy.
 *
 * **A setting is named in words, and its variable is under Advanced.** Until 2026-09-29 the list
 * read raw `INSTALL_*` names to an administrator; the API now names each by the Settings screen's
 * own words and sends the variable beside it for whoever supports the install.
 *
 * Task ids: M27.7.25, M27.16.1
 */

import { useResource } from "../../api/useResource";
import { Advanced, Fact, FactList, FailureState, LoadingState, PageHeader, SectionCard } from "../../components/kit";
import { factsOf, INSTALL_API_PATH, type InstallFacts as InstallBody } from "../installQuery";
import { InstallFacts } from "./InstallFacts";

export const INSTALL_HEADING = "This install";
export const INSTALL_LEDE = "What is actually running here, with where each statement came from beside it.";
export const READING_INSTALL = "Reading what is running here.";
export const WHAT_IS_RUNNING = "What is running";

export function InstallPage() {
  const answer = useResource<InstallBody>(INSTALL_API_PATH);
  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_INSTALL} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const facts = factsOf(answer.data);
    const settings = facts.filter((one) => (one.setting ?? "") !== "");
    content = (
      <>
        <InstallFacts facts={facts} label={WHAT_IS_RUNNING} />
        {settings.length === 0 ? null : (
          <Advanced>
            <FactList>
              {settings.map((one) => (
                <Fact key={one.name} label={one.name}>
                  <span className="font-mono text-[12px]">{one.setting}</span>
                </Fact>
              ))}
            </FactList>
          </Advanced>
        )}
      </>
    );
  }
  return (
    <div data-slot="install-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: INSTALL_HEADING }]} title={INSTALL_HEADING} lede={INSTALL_LEDE} />
      <SectionCard title={WHAT_IS_RUNNING}>{content}</SectionCard>
    </div>
  );
}
