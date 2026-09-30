/**
 * The credential field in each shape a source takes (M11.7.7): a key typed, a key file chosen and a
 * database user typed as a name and a masked password, each sent as the one string the request
 * carries, and nothing chosen or typed drawn back or held once it is sent.
 */

import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { CredentialField, credentialFor, credentialGiven, FILE_CHOSEN, PASSWORD_LABEL, USER_LABEL } from "../src/components/CredentialField";
import { useSecret } from "../src/components/ui/secret-field";

const FILE_TEXT = JSON.stringify({ type: "service_account", client_email: "a@b.example", private_key: "FILE-SENTINEL-4d2c" });

/** A form holding the credential as the connect form does, and sending it as the request would. */
function Holder({ shape, sent }: { readonly shape: string; readonly sent: string[] }) {
  const [value, setValue] = useState("");
  const [present, setPresent] = useState(false);
  const secret = useSecret();
  return (
    <div>
      <CredentialField
        shape={shape}
        id="connect-credential"
        maxChars={16000}
        value={value}
        onChange={setValue}
        secret={secret}
        onPasswordPresence={setPresent}
        disabled={false}
        problemProps={{}}
      />
      <p>{credentialGiven(shape, value, present) ? "GIVEN" : "BLANK"}</p>
      <button
        type="button"
        onClick={() => {
          sent.push(credentialFor(shape, value, secret));
          setValue("");
        }}
      >
        Send
      </button>
    </div>
  );
}

describe("a credential in its source's shape", () => {
  test("a key is typed and sent as typed", () => {
    // What breaks if this is deleted: Xero, HubSpot and Freshdesk lose the field they connect with.
    const sent: string[] = [];
    const { container } = render(<Holder shape="key" sent={sent} />);
    fireEvent.change(container.querySelector("#connect-credential") as HTMLInputElement, { target: { value: "KEY-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(sent).toEqual(["KEY-1"]);
  });

  test("a key file is chosen as a file, sent as its text, and never drawn", async () => {
    // What breaks if this is deleted: Google Drive can only be connected by pasting a private key
    // through a text box, or the file's contents are drawn on the page.
    const sent: string[] = [];
    const { container } = render(<Holder shape="key_file" sent={sent} />);
    const input = container.querySelector("#connect-credential") as HTMLInputElement;
    expect(input.type).toBe("file");
    const file = new File([FILE_TEXT], "company-brain.json", { type: "application/json" });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });
    await waitFor(() => {
      expect(container.textContent).toContain(FILE_CHOSEN);
    });
    expect(container.innerHTML).not.toContain("FILE-SENTINEL");
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(sent).toEqual([FILE_TEXT]);
    expect(container.textContent).not.toContain(FILE_CHOSEN);
  });

  test("a database user is a name and a masked password, sent as one object and then let go", () => {
    // What breaks if this is deleted: the Laravel database asks for one string and a person invents
    // a separator, the password shows in clear, or it is still in its field after the request.
    const sent: string[] = [];
    render(<Holder shape="database_user" sent={sent} />);
    const password = screen.getByLabelText(PASSWORD_LABEL) as HTMLInputElement;
    expect(password.type).toBe("password");
    fireEvent.change(screen.getByLabelText(USER_LABEL), { target: { value: "brain_reader" } });
    fireEvent.input(password, { target: { value: "PASSWORD-7" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(sent.map((one) => JSON.parse(one) as unknown)).toEqual([{ user: "brain_reader", password: "PASSWORD-7" }]);
    expect(password.value).toBe("");
    expect((screen.getByLabelText(USER_LABEL) as HTMLInputElement).value).toBe("");
  });

  test("a database user with nothing typed is nothing given, and a password alone is something", () => {
    // What breaks if this is deleted: an emptied form sends an object of two blanks, or a form with
    // only its password typed is stopped as blank before the API can say which half is missing.
    const sent: string[] = [];
    render(<Holder shape="database_user" sent={sent} />);
    expect(screen.getByText("BLANK")).toBeTruthy();
    fireEvent.input(screen.getByLabelText(PASSWORD_LABEL), { target: { value: "p" } });
    expect(screen.getByText("GIVEN")).toBeTruthy();
    fireEvent.input(screen.getByLabelText(PASSWORD_LABEL), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(sent).toEqual([""]);
  });
});
