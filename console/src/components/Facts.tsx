/**
 * A list of labelled statements about this deployment, drawn so an unknown one cannot pass for
 * a known one.
 *
 * Shared by the five install screens rather than written on each, because the rule it keeps is
 * one rule and a copy of it is a screen where somebody relaxes it. `pages/installQuery.ts` is
 * where the argument lives; this is the markup that carries it.
 *
 * **An unknown fact renders its sentence where the value would be, and there is no placeholder
 * anywhere in this file.** No dash, no "n/a", no empty cell. `brain.console.installation.Fact`
 * refuses to carry a value it does not know and requires a sentence saying what would have to
 * happen for it to be known, and a renderer supplying a dash would undo that in one line, on
 * the field somebody checks before deciding not to worry.
 *
 * **The source word is drawn beside every value, including the known ones.** It is the API's
 * own word through `Chip`, which has one appearance and no tone, so nothing here can decide
 * that `declared` is alarming or that `measured` is reassuring. A label shown only on the
 * unusual rows would be an absence a reader has to notice, which is the shape of every mistake
 * these screens are about.
 *
 * **`because` is shown on a known fact too, when the API sent one.** Several of these facts are
 * measurements of something other than what a reader assumes: the commit an image was built
 * from is not a release a client can look up, and the head the source carries is not the
 * revision the database is on. The API writes those sentences; this draws them.
 *
 * The rows use `.fields` and `.fields__row`, which is the overview's own markup and is what
 * `tests/phone-width.test.tsx` holds to a phone's width: the label sits above the value below
 * 48rem and beside it above, and the value may break inside a word. A layout of its own here
 * would be a sixth thing to keep narrow.
 */

import { Chip } from "../ui/Chip";
import { isKnown, type Fact } from "../pages/installQuery";

interface FactsProps {
  /** The statements to draw, in the order the API sent them. Never re-sorted here. */
  readonly facts: readonly Fact[];
  /** What a screen reader is told this list is. Required: an unlabelled list of values is one. */
  readonly label: string;
}

export function Facts({ facts, label }: FactsProps) {
  return (
    <dl className="fields" aria-label={label}>
      {facts.map((fact) => (
        <div className="fields__row" key={fact.name}>
          <dt>{fact.name}</dt>
          <dd>
            {/*
             * The value when there is one, and the sentence when there is not. Never both in
             * the same slot and never a placeholder: see the note at the top of this file.
             */}
            {isKnown(fact) ? <span>{fact.value}</span> : null}
            <Chip label={fact.source} />
            {fact.because ? <p className="note">{fact.because}</p> : null}
          </dd>
        </div>
      ))}
    </dl>
  );
}
