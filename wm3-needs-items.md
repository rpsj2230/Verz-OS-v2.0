## 223. What may start an automation besides the clock, and who vouches for an event that arrives from outside?

**In plain terms:** your brief says an automation can start three ways: on a schedule, when a connected
system reports a change, and when something outside calls a web address we give it. Today only the schedule
works. The other two exist as words in a list and nothing starts a run on either. Building them is not
plumbing, because each one lets something other than a person on the clock make an agent act as its owner:
a connector change is only as trustworthy as the connector's own notion of "changed", and a web address that
starts work is a door onto the internet that needs a secret, a size limit and a rule for repeats.

**Option A: schedule only, for now.** I narrow the leaf to say so and the Automations page offers one way to
start. Nothing new is exposed. A weekly report and a morning summary are covered, which is every template in
the gallery.

**Option B: schedule and connector change.** A run starts when the minimal index of a connector reports a
changed record id (never its content), and the run reads the record live as its owner, as every run does.
Nothing new faces the internet.

**Option C: all three.** B, and a signed inbound address per automation: a long secret in the address,
one body size limit, and the same body refused a second time within a day. It is the one that lets a
form on your website start work, and the one with a public door.

**My recommendation:** B now, C when a real automation needs it. B costs no new exposure and covers "when a
deal changes in HubSpot"; C is worth building the day somebody names the outside thing that should call it.
I will build either behind a switch that ships off, and prove it on your install with a changed record.

**What I need from you:** reply "223: A", "223: B" or "223: C".

## 222. May the install measure how long approvals wait across everybody, and show only the typical figure?

**In plain terms:** your brief says push notifications for approvals are held back until approvals wait
long enough to need them, and that the install should measure that wait and tell you when it passes four
hours. The measuring has not been built, because the database lets a person read only approvals they raised
or decided, so nobody on the Install page can see the whole queue's timings, and the count of approvals is
itself something the system keeps from people who may not see them.

**Option A: a counts-free view of when each approval was raised and decided.** One database view that
carries two times per decided approval and no person, no agent, no capability and no count shown to anybody.
The Install page shows one figure ("typical wait: 1 hour 40 minutes") and, past four hours, one sentence
saying push is now worth building. It needs one small database change.

**Option B: measure only what the reader may already see.** The figure is the typical wait of the
approvals the reader raised or decided. No database change, but an administrator who has decided few
approvals sees a figure about almost nothing, and the four-hour test would never fire for the install.

**Option C: do not measure; narrow the leaf.** Push stays deferred with no trigger, and I say so on the
page. I would not recommend it: the point of deferring was to let a measurement decide.

**My recommendation:** A. The figure discloses a duration and not who waited or how many, and it is the
only way the deferral's own trigger can ever fire.

**What I need from you:** reply "222: A", "222: B" or "222: C".

## 221. Who is told, and on which channel, when a safety mechanism has not run?

**In plain terms:** the system knows twenty-seven things that must keep running (the job that puts a stopped
worker's jobs back, the sweep that reads back an interrupted action, the backup, and so on) and it can tell
when one has not run for longer than it should. Today that knowledge goes nowhere: the sentence is composed
and nothing sends it, because nobody chose who hears it or where. The same is true of the alert that no
backup exists. These are the two alerts that matter most on the day something quietly breaks.

**Option A: the people who hold the operations alert, in the chat tool each last wrote on.** Told once per
episode, naming the mechanism and how long, never what it protects or any data. For the worst ones, the
people who hold the incident capability as well. Nothing is sent to anybody who cannot already open the
Install page.

**Option B: the email address you set during setup.** One message per episode to one named mailbox. It works
if the chat tools are down, and fails quietly if the mailbox is not watched.

**Option C: both.** A in chat, and B as the fallback when nobody holding the alert has used a chat tool in
the last week.

**My recommendation:** C. A mechanism that has stopped may be the one that carries the chat message, so the
mailbox is the second route that does not depend on the first. I will build it behind a switch that ships
off, and prove it on your install by pausing one mechanism and reading the message.

**What I need from you:** reply "221: A", "221: B" or "221: C".

