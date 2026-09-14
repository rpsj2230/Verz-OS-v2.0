# How to ask well

For everybody who asks this system questions. It answers from your company's own systems, and
only from what you personally may see. Seven habits get better answers out of it, and the
examples at the end of this page are chosen for each department from the records that actually
arrived for it.

## Ask about something a system of yours holds

The system answers from the sources your company has connected: its ticketing, its accounts,
its projects, its documents. A question about something none of those holds has nothing behind
it, however well it is worded. If you are not sure what is connected for your department, ask
your department's administrator, or look at the questions at the end of this page, which are
built from what is there.

## Name the thing the way the source names it

Use the client's, job's or invoice's name or reference exactly as it is written in the system it
lives in. The quickest answers match your words against that field directly, ignoring capitals.
If two records answer to the same name, the quick path will not guess which one you meant, so
use the fuller name or the reference.

## Ask one thing at a time

"How many open jobs are there?" and "Which invoice is the most recent?" are answered from a count
or a date, and those answers do not depend on how well anything was searched. A question that
bundles three things together can be answered well on two and badly on the third, and you cannot
tell which from the answer.

## Nothing found is not a no

When the system finds nothing, that is all it tells you. It does not say whether the thing does
not exist or you may not see it, and it never will: telling the two apart would tell you what
exists that is not yours. So if you expected an answer and got none, ask the person who would
know, or ask your administrator whether you should have access. Do not read the silence as a
fact about the company.

## Check the answer where it came from

Every answer is drawn from a system you can open yourself. For anything you are going to act on,
open that system and look. The first questions any department is offered each name the system to
check them in, and an answer nobody can check is not used as an example at all.

## An agent sees no more than you do

Asking through an agent never reaches anything you could not reach yourself. An agent is a
lens: it can only narrow what you see. If an agent's answer is missing something you can see
directly, that is the agent's own limit, set on purpose.

## Say when an answer is wrong

A wrong answer is usually a wrong or out-of-date document being quoted. Where the place you read
the answer offers a way to correct it, use it there and then; that is how the document gets
checked, and it stops the next person being told the same thing.

## Examples from your own department

These are the first questions each department is offered. They are not written here by hand:
they are built from the kinds of record that arrived for that department, most numerous first,
and each names where to check the answer. A department with nothing indexed is told so rather
than lent another department's questions, because a question about records you cannot reach
comes back empty, and that is a poor first day.

The questions use the source's own word for each kind of record, untranslated, which is why they
read "How many client are there?" rather than choosing a plural for somebody else's system.

On your own install the same rule builds your departments' examples from your own records. The
tables below are the demo company's four departments, as a worked case.

### Operations

<!-- checked: examples from operations -->

| Ask | Check it in |
| --- | --- |
| How many client are there? | `demo` |
| Which job is the most recent? | `demo` |

### Projects

<!-- checked: examples from projects -->

| Ask | Check it in |
| --- | --- |
| How many client are there? | `demo` |
| Which job is the most recent? | `demo` |

### Accounts

<!-- checked: examples from accounts -->

| Ask | Check it in |
| --- | --- |
| How many invoice are there? | `demo` |
| Which client is the most recent? | `demo` |

### People

<!-- checked: examples from people -->

| Ask | Check it in |
| --- | --- |
| nothing has indexed for this department yet | nowhere yet |

Two questions rather than three for the first three departments, because each has two kinds of
record indexed and a third question would repeat one of them. `demo` is the name the demo's
records are filed under; on your install it is the name of the system each record came from.

## What is checked and what is not

**Checked by `tests/unit/test_guide_docs.py`:** every table of examples above, exactly and in
order, against the questions the department's own indexed records produce; that every department
has a table and no table names a department that is not there; and that one department's
examples are never built from another department's records.

**Not checked, and kept true by hand:** the seven habits. Each is written from how the product
behaves, and none of them is a sentence a test can hold.

**Not built yet:** nothing shows a member of staff their own department's examples on a screen
or in a channel today. The rule that chooses them exists and is tested, and this page is where
they are shown.

## Task ids

M34.3.1.3
