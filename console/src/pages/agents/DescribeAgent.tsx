/**
 * Describe an agent in your own words and be taken to a draft that holds the suggestions (M20.5.3).
 *
 * **One act, confirmed, and it says where the words go.** Pressing the button asks first, because it
 * sends what the person wrote to the model provider this install uses and starts a draft of their
 * own. What comes back is not written into that draft: the Write step opens on it with the
 * suggestions drawn as before and after, none ticked, and the person takes the ones they choose
 * through the same co-author panel any suggestion is taken in. A refusal is the API's own sentence.
 *
 * **Offered only when the API says so.** `GET /agent-drafts` answers `can_describe`, and a person it
 * is false for is not shown a card their press would refuse.
 *
 * Task ids: M20.5.3
 */

import { Sparkles } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  DESCRIBE_API_PATH,
  DESCRIBE_BUTTON,
  DESCRIBE_CONSEQUENCE,
  DESCRIBE_HEADING,
  DESCRIBE_LABEL,
  DESCRIBE_LEDE,
  DESCRIBE_NEEDED,
  DESCRIBE_QUESTION,
  NOT_DESCRIBED,
  readDescribed,
} from "./agentCoauthorQuery";
import { KEEP_LABEL, draftAddress, readNotChanged } from "./agentDraftsQuery";

interface Refused {
  readonly failure: ApiFailure;
  readonly sentence?: string;
}

export function DescribeAgent() {
  const navigate = useNavigate();
  const fieldId = useId();
  const [words, setWords] = useState("");
  const [missing, setMissing] = useState(false);
  const [asking, setAsking] = useState(false);
  const [sending, setSending] = useState(false);
  const [refused, setRefused] = useState<Refused | null>(null);

  const begin = () => {
    if (words.trim() === "") {
      setMissing(true);
      return;
    }
    setMissing(false);
    setRefused(null);
    setAsking(true);
  };

  const confirm = () => {
    const described = words.trim();
    setSending(true);
    void (async () => {
      const result = await request<unknown>(DESCRIBE_API_PATH, { method: "POST", body: { description: described } });
      setSending(false);
      setAsking(false);
      if (!result.ok) {
        const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
        setRefused(notChanged === null ? { failure: result.failure } : { failure: result.failure, sentence: notChanged.sentence });
        return;
      }
      const started = readDescribed(result.data, described);
      if (started !== null) {
        navigate(draftAddress(started.draftId, "write"), { state: { described: started } });
      }
    })();
  };

  return (
    <>
      {refused === null ? null : (
        <FailureNotice
          failure={refused.failure}
          title={NOT_DESCRIBED}
          {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
        />
      )}
      <SectionCard title={DESCRIBE_HEADING} lede={DESCRIBE_LEDE} action={<Sparkles aria-hidden className="size-4 text-dim" />}>
        <div data-slot="describe-agent" className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={fieldId}>{DESCRIBE_LABEL}</Label>
            <Textarea
              id={fieldId}
              value={words}
              aria-invalid={missing}
              onChange={(event) => {
                setWords(event.target.value);
                setMissing(false);
              }}
            />
            {missing ? <p className="m-0 text-[12px] text-danger-text">{DESCRIBE_NEEDED}</p> : null}
          </div>
          <div>
            <Button className="min-h-11 sm:min-h-9" disabled={sending} onClick={begin}>
              {DESCRIBE_BUTTON}
            </Button>
          </div>
        </div>
      </SectionCard>
      <ConfirmDialog
        open={asking}
        question={DESCRIBE_QUESTION}
        consequence={DESCRIBE_CONSEQUENCE}
        confirmLabel={DESCRIBE_BUTTON}
        cancelLabel={KEEP_LABEL}
        danger={false}
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </>
  );
}
