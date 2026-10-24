/**
 * The header's language switch, drawn only when the install offers more than one (M35.1.1.1).
 *
 * Each language is named in its own words (`brain.locale.LocaleRules.endonym`), because a switch that
 * names Chinese in English is readable only by somebody who already found it. Choosing one keeps the
 * choice in this browser and reads the page again in it (`locale/index.ts` says why).
 *
 * Task ids: M35.1.1.1
 */

import { activeTag, chooseLocale, msg, offered } from "./index";

/** The control's accessible name. */
export const LANGUAGE_LABEL = msg("console.shell.language_label", "Language");

export function LanguageChoice() {
  if (offered.length < 2) {
    return null;
  }
  return (
    <label className="shell__language">
      <span className="visually-hidden">{LANGUAGE_LABEL}</span>
      <select
        value={activeTag}
        onChange={(event) => {
          chooseLocale(event.target.value);
        }}
      >
        {offered.map((one) => (
          <option key={one.tag} value={one.tag} lang={one.tag}>
            {one.endonym}
          </option>
        ))}
      </select>
    </label>
  );
}
