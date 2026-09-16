# Installing from a Windows computer, without a terminal

This page is for somebody who has been given a server and asked to install Company Brain on it,
and who does not use a terminal. You answer five questions in a window, confirm one thing, and
type your server password if you are asked for it. The helper does the rest.

**Read "Before you start" first.** Two things on it have to be true before any of this works,
and one of them is not true for anybody yet.

## Before you start

You need four things.

1. **A Windows 10 or Windows 11 computer.** Nothing needs installing on it. The helper uses
   PowerShell and the SSH program, and both come with Windows.
2. **A server running Linux**, from a hosting company or your own IT team, that you can sign in
   to. You need its **address** (a name, or four numbers with dots between them), the **user
   name** you sign in with, and either its **password** or an SSH key already set up on this
   computer. Your hosting company's welcome email usually has all three.
3. **The release page** for the version you are installing. Whoever gave you this job should
   have sent you its address.
4. **About twenty minutes**, most of it waiting.

Two things you should know now rather than later:

- **No release has been published yet.** Until one is, there is no release page to download
  from, and the helper has nothing to install. [install.md](install.md), under "What you cannot
  do today", says what is still missing.
- **The helper installs the system but does not put it on the web.** Your staff open Company
  Brain at a web address, and pointing that address at the server is a separate job for
  somebody technical, described in [network.md](network.md). You can run the helper before that
  is done.

## The steps

1. **Open the release page** in your web browser.

2. **Download two files** from it, into the same folder (your Downloads folder is fine):
   - `install-from-windows.cmd`
   - `install-from-windows.ps1`

   Both are plain text. If you want to see what they do before running them, right-click either
   one and open it with Notepad.

3. **Double-click `install-from-windows.cmd`.** A window opens.

   Windows may warn you first, because these files are not signed by a publisher it knows. The
   warning says the publisher could not be verified. If you downloaded the files from your
   release page, click **Run**. If Windows refuses to run them at all, right-click each of the
   two files, choose **Properties**, tick **Unblock** at the bottom, click **OK**, and
   double-click the `.cmd` file again.

   If the window says **the SSH program that comes with Windows is not switched on**, open
   **Settings**, then **System**, then **Optional features**, add **OpenSSH Client**, and start
   again from this step.

4. **Type your server's address** and press Enter. If your hosting company gave you a port
   number as well, type it after a colon, for example `server.example.invalid:2222`.

5. **Type the user name** you sign in to the server with, and press Enter. If you were not given
   one, press Enter and the helper uses `root`.

6. **Paste the release page's address.** Go back to your browser, click the address bar at the
   top of the release page, copy the whole address, paste it into the window, and press Enter.
   The helper shows you the release name it read from it, for example `v1.0.0`.

7. **Type a size** and press Enter. Pick the smallest one that has what you need:

   | Size | What it runs |
   | --- | --- |
   | `lite` | The application and its database. Where most companies start. |
   | `standard` | Adds background workers, a file store, a sign-in server and a local AI model. |
   | `full` | Adds a trace ledger, an automation canvas and a record matcher. |

   If you are not sure, type `lite`. [install.md](install.md), under "Sizing", says how big a
   server each size needs, and the installer refuses a server that is too small before it
   changes anything.

8. **Type the web address** your staff will use, for example `https://brain.example.invalid`,
   and press Enter. If nobody has decided it yet, just press Enter.

9. **Check who the server says it is.** The window shows a line beginning with `SHA256:`. That
   is your server's fingerprint, and it is how you know you are talking to your own server and
   not to something pretending to be it.
   - If your hosting company showed you a fingerprint for this server, check that it is the
     same. If it is not, type `no` and ask them why.
   - If you created the server yourself a short while ago and have nothing to compare it with,
     it is usual to go on.

   Type `yes` and press Enter to go on.

10. **Type `yes` to start the install.** The window shows what it is about to install, and where.

11. **Type your password if you are asked for it.** The server may ask once to let you in and
    once more to install. Nothing appears on the screen while you type a password; that is
    normal. Press Enter after it.

12. **Wait.** The install prints what it is doing, step by step, and takes several minutes. Leave
    the window open.

13. **Copy the setup code.** When the install finishes, the window says so. A few lines above
    that there is a line beginning with `setup code:`. Select the long code after it and copy
    it. You need it next, and it is only shown here.

14. **Finish setup in your browser.** Open your web address followed by `/first-run`, for
    example `https://brain.example.invalid/first-run`. Sign in, and enter the setup code when
    you are asked for it. **Do this straight away:** until somebody does, whoever opens that
    address first becomes the administrator.

15. **Press Enter** to close the helper's window.

## If something goes wrong

**"That address could not be found."** The address has a typing mistake, or the server's name
has not been set up yet. Check the welcome email from your hosting company and start again.

**"The server did not answer."** The server is switched off, the address is wrong, or a firewall
is blocking SSH. Check the server is running in your hosting company's control panel.

**"The server refused the connection."** SSH is not running on the server, or it uses a
different port. Ask your hosting company which port to use, and type the address as
`address:port`.

**"Permission denied."** The user name or the password is wrong, or the server only accepts an
SSH key and this computer does not have it. Check them with whoever gave you the server.

**"Host key verification failed."** The server presented a different identity from the one you
confirmed. Stop and ask whoever runs the server before trying again.

**"sudo: command not found" or "is not in the sudoers file".** The user you signed in as is not
allowed to install software. Ask your hosting company for a user that can use `sudo`.

**"The install stopped before it finished."** The lines just above that message say what went
wrong and what to do about it. Once it is fixed, run the helper again from step 3: the install
is safe to run twice and skips what it has already done.

**The window closed before you copied the setup code.** Somebody with access to the server can
read it again: running the install a second time prints the same code.

## What the helper does, and what it never does

It asks your five answers, checks each one is the shape it should be before using it, asks your
server who it is without offering it anything, shows you the answer, and then runs this one
command on the server, exactly as [install.md](install.md) documents it. Both addresses are the
files of that name on your release page:

```
curl -fsSL <address of install.sh> -o install.sh && sudo BRAIN_RELEASE_URL=<address of the archive> bash install.sh --release <release> --profile <size> --console-address <web address>
```

The only difference from that page is the step where a person reads the script before running
it, which the helper cannot do for you.

It **never asks for or keeps a password**: when the server wants one, Windows' own SSH program
asks you directly. It **never saves your answers**. The only file it writes is the server's
public identity, in a temporary folder it deletes before it finishes. And it **never reads the
setup code**: the installer prints the code in the window, and you copy it from there.

It **only fetches a release over `https://`**, because the install runs what it downloads with
full control of the server, and an address anybody on the network could tamper with would hand
them that control.

## What is checked and what is not

| Claim | Held by |
| --- | --- |
| The command the helper runs on the server is the one install.md documents | `tests/unit/test_windows_helper.py`, running the helper against a stand-in for SSH |
| It confirms the server's identity before offering anything, and accepts only that identity afterwards | the same, from the arguments SSH received |
| It refuses an address that is empty, malformed, not https, or begins with a dash | the same |
| It leaves nothing behind and writes nothing secret | the same, by looking |
| It works in the restricted mode Windows runs an unsigned script in | the same, run in that mode |
| The release carries both files and publishes them beside the archive | `test_windows_helper.py`, against the release workflow |
| **That it installs anything, because it has ever been run against a real server** | **nobody. No release has been published.** |
| **Every sentence under "If something goes wrong"** | **nobody. Kept true by hand.** |

## Task ids

M42.6.6 is claimed for the helper, its launcher and this page. It has never installed anything
on a real server, which is stated above rather than left to be discovered.
