/**
 * What can be done to a webhook subscriber from the Webhooks module, one label each.
 *
 * **Every act has a route, so none is drawn inert.** Until 2026-10-06 switching a subscriber back on
 * and replaying a delivery that was given up were `kit/UnavailableAction` with a sentence each,
 * because neither could be recorded: `ops.webhook_subscriber`'s policy let a row change only while it
 * was on, and `ops.webhook_change` had no word for either act. `0210` added both, and the API serves
 * `POST /webhooks/subscribers/{id}/switch-on` and `POST /webhooks/subscribers/{id}/deliveries/{name}
 * /replay`, so both are live controls sent from a confirmation in the API's words, as the other three
 * are. `tests/webhooks-page.test.tsx` holds each label to the control that draws it.
 *
 * Task ids: M27.8.12, M27.15.44, M27.16.1
 */

/** The labels of the acts, one spelling each, so a menu and a test agree. */
export const ACT_LABELS = Object.freeze({
  open: "Open",
  register: "Register a subscriber",
  reviewRegistration: "Register",
  replace: "Replace secret",
  switchOff: "Switch off",
  switchOn: "Switch back on",
  replay: "Replay",
});
