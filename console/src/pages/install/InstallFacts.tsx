/**
 * The install screens' labelled statements on the kit: each fact with its value when it is known,
 * its source word always, and the API's sentence saying why.
 *
 * `components/Facts.tsx`' rules, drawn with the kit's parts for the pages rebuilt on it (the Recovery,
 * Limits and Capacity pages keep that component until they are rebuilt). **A fact keeps its source
 * label; an unknown fact draws its sentence and no value, never a dash; no value picks a colour.**
 * See `installQuery.ts`' three rules. The value is marked `data-slot="fact-value"`, so a test can
 * hold that an unknown fact has none rather than guessing how a placeholder might be spelled.
 *
 * Task ids: M27.7.25, M27.16.1
 */

import { Chip, Fact } from "../../components/kit";
import { isKnown, type Fact as InstallFact } from "../installQuery";

/** What a list with nothing in it says. */
export const NO_FACTS = "Nothing was reported here.";

export function InstallFacts({ facts, label }: { readonly facts: readonly InstallFact[]; readonly label: string }) {
  if (facts.length === 0) {
    return <p className="m-0 text-[12.5px] text-dim">{NO_FACTS}</p>;
  }
  return (
    <dl data-slot="fact-list" aria-label={label} className="m-0 flex min-w-0 flex-col">
      {facts.map((fact) => (
        <Fact key={fact.name} label={fact.name}>
          <span className="flex flex-wrap items-center gap-2">
            {isKnown(fact) ? (
              <span data-slot="fact-value" className="font-mono text-[12.5px]">
                {fact.value}
              </span>
            ) : null}
            <Chip>{fact.source}</Chip>
          </span>
          {fact.because ? <p className="m-0 mt-1 text-[12px] leading-snug text-dim">{fact.because}</p> : null}
        </Fact>
      ))}
    </dl>
  );
}
