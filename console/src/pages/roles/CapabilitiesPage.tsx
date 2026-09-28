/**
 * The Capabilities tab of Roles and permissions: everything that can be granted at all, and what
 * each one reaches.
 *
 * **Whole, or nothing, and never narrowed to what the reader holds.**
 * `brain.console.govern.catalogue` decides that and says why narrowing is the attractive mistake: a
 * reader shown only what they hold, under a heading reading everything that can be granted, is told
 * the vocabulary is smaller than it is. A reader without the grant is answered an empty list, and the
 * empty sentence here is true for every reason it could be empty.
 *
 * **The search box narrows words on the screen, not the answer.** It filters the rows already drawn
 * by what the reader typed, which is not a permission filter: every row was sent, and none is
 * withheld by typing. There is no count, because the list is whole and the list says itself.
 *
 * **The vocabulary is declared by the product, not edited here** (Part 3, B3: Imp N), which a sentence
 * says rather than a disabled control.
 *
 * Task ids: M27.11.3, M27.7.6, M27.16.1
 */

import { KeyRound, Search } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useResource } from "../../api/useResource";
import {
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  NotOffered,
  PageHeader,
  SectionCard,
  type EntityColumn,
} from "../../components/kit";
import { Input } from "../../components/ui/input";
import { CAPABILITIES_API_PATH, readCapabilities, type CapabilityRow } from "../governQuery";
import { ROLES_HEADING } from "./RolesPage";

export const CAPABILITIES_CRUMB = "Capabilities";
export const CAPABILITIES_LEDE = "Everything that can be granted at all, and what each one reaches. Read this before writing a grant.";
export const NO_CAPABILITIES = "No capabilities to show";
export const NO_CAPABILITIES_DESCRIPTION =
  "The vocabulary is declared by the tools and connected sources this install has, and is shown to a reader who may name capabilities.";
export const THE_VOCABULARY_IS_DECLARED =
  "Capabilities are declared by the product's tools and the sources connected to it, so they are not added or edited here.";

const COLUMNS: readonly EntityColumn<CapabilityRow>[] = [
  {
    id: "capability",
    header: "Capability",
    hideable: false,
    cell: (row) => <code className="font-mono text-[12px] [overflow-wrap:anywhere]">{row.capability}</code>,
    text: (row) => row.capability,
  },
  { id: "description", header: "What it reaches", cell: (row) => row.description, text: (row) => row.description },
];

export function CapabilitiesPage() {
  const answer = useResource<unknown>(CAPABILITIES_API_PATH);
  const all = useMemo(() => readCapabilities(answer.data), [answer.data]);
  const [typed, setTyped] = useState("");
  const searchId = useId();
  const words = typed.trim().toLowerCase();
  const shown = words === "" ? all : all.filter((one) => `${one.capability} ${one.description}`.toLowerCase().includes(words));

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (answer.data === null) {
    body = <LoadingState label="Loading the capabilities." />;
  } else if (all.length === 0) {
    body = <EmptyState title={NO_CAPABILITIES} description={NO_CAPABILITIES_DESCRIPTION} icon={<KeyRound aria-hidden />} />;
  } else if (shown.length === 0) {
    body = <EmptyState title="Nothing matches" description="Change the words in the search box." />;
  } else {
    body = <EntityTable caption="Every capability" columns={COLUMNS} rows={shown} rowId={(row) => row.capability} rowLabel={(row) => row.capability} exportName="capabilities" />;
  }

  return (
    <div data-slot="capabilities-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: ROLES_HEADING }, { label: CAPABILITIES_CRUMB }]} title={CAPABILITIES_CRUMB} lede={CAPABILITIES_LEDE} />
      <SectionCard title="The vocabulary" footer={<NotOffered>{THE_VOCABULARY_IS_DECLARED}</NotOffered>}>
        <div className="flex min-w-0 flex-col gap-3">
          {all.length === 0 ? null : (
            <span className="relative flex w-full min-w-0 items-center sm:w-72">
              <label htmlFor={searchId} className="sr-only">
                Search the capabilities
              </label>
              <Search aria-hidden className="pointer-events-none absolute left-2.5 size-4 text-dim" />
              <Input
                id={searchId}
                type="search"
                className="h-11 pl-8 sm:h-8"
                placeholder="Search capabilities"
                value={typed}
                onChange={(event) => {
                  setTyped(event.target.value);
                }}
              />
            </span>
          )}
          {body}
        </div>
      </SectionCard>
    </div>
  );
}
