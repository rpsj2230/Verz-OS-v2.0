/**
 * The page cases for `/notifications`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const NOTIFICATIONS = {
  notices: [
    {
      kind: "reverification_request",
      title: UNBROKEN,
      told: UNBROKEN,
      about: UNBROKEN,
      how: UNBROKEN,
      sent: true,
      switchable: true,
      fixed_because: "",
      on: false,
      changed_by: UNBROKEN,
      changed_at: "2019-03-04T09:00:00Z",
    },
    {
      kind: "emergency_access",
      title: UNBROKEN,
      told: UNBROKEN,
      about: UNBROKEN,
      how: UNBROKEN,
      sent: false,
      switchable: false,
      fixed_because: UNBROKEN,
      on: true,
      changed_by: null,
      changed_at: null,
    },
  ],
  email: {
    configured: true,
    host: `${UNBROKEN}.example.test`,
    port: 587,
    security: "starttls",
    sender: `${UNBROKEN}@example.test`,
    username: UNBROKEN,
    changed_by: UNBROKEN,
    changed_at: "2019-03-04T09:00:00Z",
    password: { held: null, written_at: null, vault: "unreachable", vault_told: UNBROKEN },
  },
  securities: ["starttls", "tls"],
  email_used_for: UNBROKEN,
  subscribers: UNBROKEN,
  ships_on: UNBROKEN,
  only_the_last_change_is_kept: UNBROKEN,
  switching_off: UNBROKEN,
  switching_on: UNBROKEN,
  saving_email: UNBROKEN,
  keeping_password: UNBROKEN,
  sending_trial: UNBROKEN,
  removing_email: UNBROKEN,
  plain_smtp_refused: UNBROKEN,
  people: { [UNBROKEN]: UNBROKEN },
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Notifications and email. The notice table scrolls; the relay's facts, the password line and
  // the sentences wrap. No control is pressed here: `tests/notifications-page.test.tsx` holds the
  // drawers and dialogs.
  "/notifications": {
    address: "/notifications",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/notifications": NOTIFICATIONS },
  },
};
