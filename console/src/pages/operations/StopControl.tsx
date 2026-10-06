/**
 * The Stop control in the header of every console page, for a reader who holds the stop (M27.15.14).
 *
 * **Drawn only when the menu says so.** `brain.navigation_routes.stop_offered` decides, on the
 * server, whether this reader may open the Stop screen and whether their stop reaches everything or
 * only their departments, and the shell passes that down. The menu is the one answer every page
 * already reads, so the control costs no request of its own and the browser holds no copy of who may
 * stop what (`THE_STOP_CONTROL_RIDES_ON_THE_MENU`).
 *
 * **One press, no confirmation and no words.** For a reader whose stop reaches everything it stops
 * everything; for a department administrator it stops each department their console names, which is
 * all their scope reaches. No reason is sent, and the API stores the fixed sentence with who pressed
 * it and when (`brain.ops.halt_store.A_STOP_NEEDS_NO_WORDS_AND_A_RESUME_DOES`). Once pressed it says
 * so and links to the Stop screen, where resuming is.
 *
 * Task ids: M27.15.14, M27.12.4
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import { Button } from "../../components/ui/button";
import type { StopOffer } from "../../layout/navigationQuery";
import { HALTS_API_PATH, NOT_STOPPED, oneTouchStops, STOP_EVERYTHING, STOP_LABEL, STOP_PATH, stopBody, STOPPED_STATUS } from "../stopQuery";

export function StopControl({ stop, departments }: { readonly stop: StopOffer; readonly departments: readonly string[] }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<"" | "stopped" | "refused">("");
  const presses = oneTouchStops(stop, departments);
  if (presses.length === 0) {
    return null;
  }

  function press(): void {
    setBusy(true);
    void (async () => {
      let refused = false;
      for (const one of presses) {
        const result = await request<unknown>(HALTS_API_PATH, { method: "POST", body: stopBody(one.scope, one.target, "") });
        refused = refused || !result.ok;
      }
      setBusy(false);
      setDone(refused ? "refused" : "stopped");
    })();
  }

  return (
    <div data-slot="stop-control" className="flex items-center gap-2">
      {done === "stopped" ? (
        <Link to={STOP_PATH} role="status" className="text-[12.5px] font-medium text-destructive underline-offset-4 hover:underline">
          {STOPPED_STATUS}
        </Link>
      ) : null}
      {done === "refused" ? (
        <span role="alert" className="text-[12px] text-crit">
          {NOT_STOPPED}
        </span>
      ) : null}
      <Button
        type="button"
        variant="destructive"
        className="min-h-11 sm:min-h-9"
        disabled={busy}
        aria-label={stop === "everything" ? STOP_EVERYTHING : `${STOP_LABEL}: ${departments.join(", ")}`}
        onClick={press}
      >
        {STOP_LABEL}
      </Button>
    </div>
  );
}
