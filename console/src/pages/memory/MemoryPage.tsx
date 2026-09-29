/**
 * Memory on the shared page kit: choose a person by name, then read what the system remembers about
 * them in its own words, one statement at a time, and every change to it.
 *
 * **One person at a time, and never a list of whose memory exists.** A list of the people the system
 * remembers things about is a directory of people, which `brain.console.govern_estate.
 * A_MEMORY_VIEWER_OVER_EVERY_SUBJECT_IS_A_DIRECTORY_OF_PEOPLE` refuses. So the bare address offers
 * the People directory's own search, which answers only people this reader may already see and says
 * nothing about memory, and the person's page is at an address of its own (`MemoryDetailPage.tsx`).
 * Typing a reference, which nobody knows, is kept in Advanced for a support request.
 *
 * **Nothing here asks the API until somebody types**, so the page is excused from the arrival
 * states in `tests/support/screenStateRules.tsx` for the reason it always was.
 *
 * Removed from the old screen: the reference box as the only way in, and its paragraph about the
 * People screen's reference format.
 *
 * Task ids: M27.7.22, M27.16.1
 */

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Advanced, PageHeader, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { PersonPicker } from "../access/PersonPicker";
import { memoryAddress, referenceProblem } from "../memoryQuery";

export const MEMORY_HEADING = "Memory";
export const MEMORY_LEDE =
  "What the system remembers about a person, in its own words, with every change to it. Memory is read one person at a time.";
export const CHOOSE_HEADING = "Whose memory";
export const CHOOSE_LEDE = "Choose a person by name. Only people you may see are offered.";
export const REFERENCE_LABEL = "Open by reference";
export const REFERENCE_HINT = "The person's reference, as a support request quotes it: no spaces, up to 64 characters.";

function ByReference() {
  const navigate = useNavigate();
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = referenceProblem(typed.trim());
    setProblem(found);
    if (found === null) {
      navigate(memoryAddress(typed.trim()));
    }
  };

  return (
    <form aria-label={REFERENCE_LABEL} className="flex min-w-0 flex-col gap-2" noValidate onSubmit={submit}>
      <label htmlFor="memory-reference" className="text-[13px] font-medium text-ink">
        {REFERENCE_LABEL}
      </label>
      <p id="memory-reference-hint" className="m-0 text-[12px] leading-snug text-dim">
        {REFERENCE_HINT}
      </p>
      <span className="flex flex-wrap items-center gap-2">
        <Input
          id="memory-reference"
          className="h-11 w-full min-w-0 sm:h-9 sm:w-72"
          autoComplete="off"
          spellCheck={false}
          aria-describedby="memory-reference-hint"
          aria-invalid={problem === null ? undefined : true}
          value={typed}
          onChange={(event) => {
            setTyped(event.target.value);
          }}
        />
        <Button type="submit" variant="outline" size="sm" className="min-h-11 sm:min-h-8">
          Open
        </Button>
      </span>
      {problem === null ? null : <p className="m-0 text-[12px] text-crit">{problem}</p>}
    </form>
  );
}

/** The bare address, and a person's address whose reference could not be asked about. */
export function MemoryPage({ problem = null }: { readonly problem?: string | null | undefined }) {
  const navigate = useNavigate();
  return (
    <div data-slot="memory-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: MEMORY_HEADING }]} title={MEMORY_HEADING} lede={MEMORY_LEDE} />
      <SectionCard title={CHOOSE_HEADING} lede={CHOOSE_LEDE}>
        <PersonPicker
          label="Person"
          chosen={null}
          onChoose={(person) => {
            if (person !== null) {
              navigate(memoryAddress(person.principalId));
            }
          }}
        />
      </SectionCard>
      {problem === null ? null : (
        <p role="alert" className="m-0 text-[13px] text-crit">
          {problem}
        </p>
      )}
      <Advanced>
        <ByReference />
      </Advanced>
    </div>
  );
}
