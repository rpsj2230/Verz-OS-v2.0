"""Normalisation, held to the two things it must never do.

It must never let two different companies become one key, and it must never quietly produce a
key that matches everything. Almost every test here is one of those two, because a normaliser
is easy to test wrongly: a function returning the empty string passes every test that only
checks what was stripped, and a function that deletes its input passes every test whose input
was already normalised. So every stripping test has a sibling proving a real name survives, and
every input contains something the rule under test actually changes.

Task ids: M14.2.1, M14.2.2, M14.2.3, M14.2.4, M14.2.5, M14.2.6
"""

from __future__ import annotations

import unicodedata
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pytest

from brain.resolution.normalise import (
    ACCENT_FOLD_ID,
    IMMUTABLE_UNACCENT_SQL,
    MIN_KEY_CHARS,
    MIN_TRIGRAMS_FOR_A_MEASUREMENT,
    NON_DECOMPOSING_LATIN,
    ROUTES_TO_REVIEW,
    SUFFIX_TOKENS,
    NameVerdict,
    UenCheck,
    UenKind,
    _fold_id,
    accent_fold,
    check_uen,
    collapse,
    normalise_name,
    strip_suffixes,
)

REPO = Path(__file__).resolve().parents[2]

#: The eight legal forms M14.2.3 names, written out here rather than imported, so that this
#: file disagrees with the module when somebody adds a ninth instead of agreeing by
#: construction.
LEAF_SUFFIXES = ("Pte Ltd", "Pte", "Sdn Bhd", "Inc", "LLC", "Limited", "Ltd", "Co")


# ------------------------------------------------- case and whitespace (M14.2.1)
def test_case_and_spacing_differences_do_not_survive_normalisation() -> None:
    """Two sources spelling one company differently produce one key.

    The input is deliberately the awkward form rather than an already-tidy one: leading and
    trailing spaces, doubled spaces between tokens, capitals and full stops. A test written
    against "acme" would pass with every rule in `collapse` deleted, because there would be
    nothing left for any of them to do.

    Delete this and the collapse can stop collapsing without a single test noticing, and two
    Freshdesk and Xero records for one client stop joining."""
    messy = normalise_name("  ACME   Pte.  Ltd.  ")
    tidy = normalise_name("acme pte ltd")

    assert messy.key == "acme"
    assert messy.key == tidy.key
    assert messy.observed == "  ACME   Pte.  Ltd.  ", "the observed form is evidence and is kept"


def test_two_different_companies_do_not_normalise_to_one_key() -> None:
    """The other half of the rule above, and the half a normaliser fails silently.

    Every test in this file that asserts two spellings agree is also passed by a function that
    returns a constant. This one is not: two names that differ by one letter, and by one token,
    have to come out different.

    Delete this and a normaliser that dropped vowels, truncated to four characters or returned
    the empty string would pass the rest of the file, and the cascade would merge the estate."""
    assert normalise_name("ACME Pte Ltd").key != normalise_name("ACMO Pte Ltd").key
    assert normalise_name("Acme Trading").key != normalise_name("Acme Holdings").key
    assert normalise_name("Acme Trading").key == "acme trading", "and it is not truncated"


def test_an_invisible_character_does_not_split_a_name() -> None:
    """A zero-width space inside a name is removed, not turned into a boundary.

    `str.isspace()` is False for U+200B, U+200C and U+FEFF, so a whitespace collapse alone
    leaves them in and the key silently stops matching its twin. They are also invisible, so
    nobody debugging the miss can see the difference between the two names.

    Delete this and a name pasted out of a spreadsheet stops joining to the same name typed
    into a form, and the two look identical in every log line about it."""
    for invisible in ("\u200b", "\u200c", "\ufeff", "\u2060"):
        assert normalise_name(f"AC{invisible}ME Pte Ltd").key == "acme", f"{invisible!r} survived"


def test_a_non_breaking_space_is_collapsed_like_any_other_space() -> None:
    """The spaces a word processor inserts are spaces.

    Separate from the test above because they fail differently: a non-breaking space is caught
    by `str.split`, a zero-width one is not, and one rule covering both would be an accident
    rather than a decision.

    Delete this and a name copied out of a document keeps a space nobody can see the type
    of."""
    assert normalise_name("ACME\u00a0Pte\u3000Ltd").key == "acme"


def test_case_folding_rather_than_lower_casing_is_what_maps_the_sharp_s() -> None:
    """`str.lower` leaves U+00DF alone and `str.casefold` maps it to "ss". NFKD does neither.

    The two facts are asserted rather than assumed, because the whole reason `collapse` uses
    the more obscure of the two methods is this one letter, and "lower is simpler" is the edit
    somebody makes on a quiet afternoon.

    Delete this and both case folds become `lower`, every other test in this file still passes,
    and every German name in the estate splits into two entities depending on which of two
    spellings the source used."""
    assert unicodedata.normalize("NFKD", "\u00df") == "\u00df", "NFKD does not touch it"
    assert "\u00df".lower() == "\u00df", "and neither does lower"
    assert "\u00df".casefold() == "ss"

    assert normalise_name("Gro\u00dfe Ltd").key == normalise_name("Grosse Ltd").key == "grosse"


def test_a_capital_reaches_the_named_fold_in_the_form_that_map_is_keyed_in() -> None:
    """**The job of the first of the two case folds, found by a mutation run.**

    `NON_DECOMPOSING_LATIN` is keyed in lower case. Without a fold in front of it, U+00D8 in a
    name written in capitals never meets the map, passes through NFKD untouched because it
    carries no combining mark, and reaches the key as itself, where Postgres's `unaccent.rules`
    would have folded it to "o". That is precisely the disagreement between the two
    implementations that makes a join miss with nothing reporting it.

    Delete this and the first fold reads as redundant beside the second one and gets removed,
    and every Nordic name written in capitals by one source stops matching itself."""
    assert normalise_name("M\u00d8LLER Ltd").key == "moller"
    assert normalise_name("M\u00f8ller Ltd").key == "moller"


def test_a_decomposition_that_produces_capitals_is_folded_back_down() -> None:
    """The job of the second of the two case folds.

    NFKD's compatibility decompositions expand U+2121 to "TEL" and U+216B to "XII", both in
    capitals, and a key that differs by case is a key that does not join. The first fold cannot
    do this, because the capitals do not exist until after it has run.

    Delete this and the second fold reads as a duplicate of the first and gets removed, and a
    name carrying one of these characters produces a key nothing else ever matches."""
    assert normalise_name("\u2121 Services").key == "tel services"
    assert normalise_name("\u216b Trading").key == "xii trading"


# ------------------------------------------------------- punctuation (M14.2.2)
def test_punctuation_becomes_a_token_boundary_so_a_suffix_can_still_be_found() -> None:
    """This is why punctuation is replaced with a space rather than deleted.

    "ABC Pte.Ltd." with the full stops deleted is the single token "abcpteltd", and no
    whole-token suffix rule can find anything inside it, so the legal form stays on the key and
    the name never matches the same company written "ABC Pte Ltd".

    Delete this and somebody optimises the punctuation step to a `str.replace` with an empty
    string, every test about accents and case still passes, and suffix stripping silently stops
    working on any source that writes its punctuation tightly."""
    assert normalise_name("ABC Pte.Ltd.").key == "abc"
    assert normalise_name("ABC Pte Ltd").key == "abc"


def test_an_apostrophe_is_deleted_rather_than_made_into_a_boundary() -> None:
    """An apostrophe inside a word is a mark on a letter, not a gap between two words.

    Both the straight and the curly form, because a name typed into a form carries one and a
    name pasted out of a document carries the other, and those are the same company.

    Delete this and "O'Brien" becomes "o brien", which agrees with neither "OBrien" nor
    anything else, and the smart-quote version becomes a third key again."""
    straight = normalise_name("O'Brien Ltd")
    curly = normalise_name("O\u2019Brien Ltd")

    assert straight.key == "obrien"
    assert straight.key == curly.key


def test_an_ampersand_and_a_space_produce_one_key_and_that_is_the_cost() -> None:
    """The stated cost of treating every symbol as a boundary, pinned so it stays stated.

    "A&B Trading" and "A B Trading" become one key. That is the intended behaviour of
    punctuation stripping and it is also a real loss, and pinning it means a later author
    changing their mind has to change a test with the argument written on it rather than
    discovering the behaviour in production.

    Delete this and the trade-off in the module docstring stops being checked by anything."""
    assert normalise_name("A&B Trading").key == normalise_name("A B Trading").key == "a b trading"


# ---------------------------------------------------- suffix stripping (M14.2.3)
def test_a_suffix_comes_off_only_as_a_whole_token() -> None:
    """The classic implementation of suffix stripping is a substring replace, and it is wrong.

    "Incorporated Systems" contains "Inc" and "Sincere Trading" contains "inc", and a substring
    rule mangles both into names no source ever wrote. The test asserts the surviving text
    rather than merely that something survived, because a rule that stripped the wrong three
    characters would still leave a non-empty key.

    Delete this and `key.replace("inc", "")` reads as a simplification, passes every other test
    in this file, and rewrites a fifth of the client list."""
    assert normalise_name("Incorporated Systems").key == "incorporated systems"
    assert normalise_name("Sincere Trading").key == "sincere trading"
    assert normalise_name("Sincere Trading Co").key == "sincere trading", "and the real one goes"


def test_a_suffix_is_stripped_from_the_end_and_nowhere_else() -> None:
    """A legal form in the middle of a name is part of the name.

    "Pte Ltd Trading" is a company called that. Nothing is stripped, because the last token is
    not a legal form, and the rule stops at the first token that is not one rather than
    scanning the whole list.

    Delete this and a rule that removed every suffix token wherever it sat would pass the
    ordinary cases and would turn this name into "trading", which then matches every other
    trading company in the estate."""
    assert normalise_name("Pte Ltd Trading").key == "pte ltd trading"


def test_every_legal_form_the_leaf_names_is_stripped_and_a_form_it_does_not_name_is_kept() -> None:
    """M14.2.3 lists eight forms. All eight come off; nothing else does.

    The list is written out at the top of this file rather than imported from the module, so
    that adding a ninth token to `SUFFIX_TOKENS` fails here instead of being agreed with by a
    test that reads the same set it is checking.

    The negative half matters as much: "Corp", "Pty" and "GmbH" are legal forms too and are
    deliberately not in the set, because every addition re-normalises every name already
    stored and merges pairs that were separate the day before.

    Delete this and the set can gain or lose a member with nothing failing."""
    for suffix in LEAF_SUFFIXES:
        assert normalise_name(f"Alpha {suffix}").key == "alpha", f"{suffix} was not stripped"
    for kept in ("Corp", "Corporation", "Pty", "GmbH", "Holdings"):
        assert normalise_name(f"Alpha {kept}").key == f"alpha {kept.lower()}", f"{kept} was cut"


def test_a_name_that_is_entirely_a_legal_form_is_not_stripped_to_nothing() -> None:
    """**The empty key is the failure this whole module is arranged against.**

    "Pte Ltd" stripped of its suffixes is the empty string, and the empty string is equal to
    the empty string, so every degenerate row in the estate would join every other one into a
    single entity holding unrelated companies. The strip refuses to remove the last token, the
    verdict routes the row to a person, and `match_key` is None so a caller that skipped the
    verdict joins on nothing rather than on "".

    Delete this and the guard inside `strip_suffixes` can be removed as redundant, every other
    suffix test still passes, and the first backfill produces one entity for every company
    whose name field held only a legal form."""
    result = normalise_name("Pte Ltd")

    assert result.key == "pte ltd", "the observed form is kept rather than emptied"
    assert result.removed == (), "and nothing was recorded as stripped"
    assert result.verdict is NameVerdict.ENTIRELY_A_SUFFIX
    assert result.match_key is None, "so nothing can join on it"


def test_a_single_token_that_is_a_legal_form_is_caught_too() -> None:
    """The one-token version of the case above, which a length check afterwards would miss.

    "Co" strips to nothing by exactly the same route, and it is the shorter case an author
    testing only "Pte Ltd" would not think of.

    Delete this and a guard written as "refuse a key under two characters" passes the two-token
    case and lets this one through."""
    assert normalise_name("Co").verdict is NameVerdict.ENTIRELY_A_SUFFIX
    assert normalise_name("Co").match_key is None


def test_strip_suffixes_reports_what_it_removed_in_the_order_it_was_written() -> None:
    """The removals are evidence for a reviewer and have to be readable as such.

    Asserted on the tuple rather than on its length, because the order is what makes it
    readable: "pte", "ltd" is what the source wrote and "ltd", "pte" is the order the loop
    happened to pop them in.

    Delete this and the removals can come back reversed, which reads to a reviewer as a name
    nobody ever wrote."""
    kept, removed = strip_suffixes(("acme", "pte", "ltd"))

    assert kept == ("acme",)
    assert removed == ("pte", "ltd")


def test_two_legal_forms_of_one_company_agree_and_the_unstripped_forms_do_not() -> None:
    """The dangerous half of suffix stripping, pinned in both directions.

    "ABC Pte Ltd" and "ABC Ltd" produce one key, which is what the leaf asks for and is almost
    always right. The two `collapsed` forms stay different, which is what lets M14.3.2 tell
    "these agreed on their full names" from "these agreed only after their legal forms came
    off" and ask for corroboration for the second.

    Delete this and somebody collapses the two fields into one, which reads as removing a
    duplicate, and the distinction M14.3.2 needs no longer exists anywhere."""
    long_form = normalise_name("ABC Pte Ltd")
    short_form = normalise_name("ABC Ltd")

    assert long_form.key == short_form.key == "abc"
    assert long_form.collapsed != short_form.collapsed
    assert long_form.collapsed == "abc pte ltd"


# ---------------------------------------------------- accent folding (M14.2.4)
def test_an_accent_does_not_change_a_key() -> None:
    """The ordinary case: a letter that decomposes into a base and a combining mark.

    Delete this and the fold can stop dropping combining marks, and every client whose name
    carries one becomes two entities depending on which source spelled it which way."""
    assert normalise_name("Caf\u00e9 Ltd").key == normalise_name("Cafe Ltd").key == "cafe"


def test_a_letter_that_does_not_decompose_is_folded_by_the_named_map() -> None:
    """**The half of the fold NFKD cannot do, proved by showing NFKD not doing it.**

    U+00F8 and U+0142 carry no combining mark, so `unicodedata` leaves them exactly as they
    are; the first assertion is that fact rather than an assumption about it. Postgres's
    `unaccent.rules` maps them, because it is a lookup table rather than a decomposition, so
    without `NON_DECOMPOSING_LATIN` the Python fold and the database fold disagree on precisely
    these letters and the join silently misses.

    Delete this and the map reads as belt and braces over NFKD, gets removed as redundant, and
    every Nordic and Central European name in the estate stops matching itself."""
    assert unicodedata.normalize("NFKD", "\u00f8") == "\u00f8", "NFKD does not touch it"
    assert unicodedata.normalize("NFKD", "\u0142") == "\u0142"

    assert accent_fold("\u00f8") == "o"
    assert normalise_name("Ma\u00f8rsk Ltd").key == "maorsk"
    assert normalise_name("\u0141ukasz Trading").key == "lukasz trading"


def test_the_fold_id_changes_when_the_fold_changes() -> None:
    """A stored key can be checked against the fold that made it, and only if the id moves.

    The id is derived from the rule table rather than typed, because a hand-maintained version
    string is one somebody forgets to bump, and the forgetting is invisible: an index keeps the
    id it was built with while the fold quietly starts producing something else.

    Asserted by computing the id for a table with one entry removed, rather than by comparing
    `ACCENT_FOLD_ID` with itself.

    Delete this and `_fold_id` can be replaced by a constant string, every other test passes,
    and a re-normalisation becomes undetectable."""
    smaller = {key: value for key, value in NON_DECOMPOSING_LATIN.items() if key != "\u00f8"}

    assert _fold_id(smaller) != ACCENT_FOLD_ID
    assert normalise_name("anything at all").fold == _fold_id(NON_DECOMPOSING_LATIN)


def test_the_immutable_wrapper_names_its_dictionary_explicitly() -> None:
    """The wrapper has to call the two-argument form, and that is the whole of the trick.

    The one-argument `unaccent(text)` resolves its dictionary through `search_path`, which is
    one of the two reasons PostgreSQL declares it STABLE; the two-argument form takes a
    `regdictionary` and removes that dependence. A wrapper declared IMMUTABLE around the
    one-argument call is the version that looks right, builds an index, and is wrong in a way
    the planner will never tell anybody about.

    Delete this and the constant can be simplified to the one-argument call while still saying
    IMMUTABLE, which is the exact trap M14.2.4 names."""
    assert "IMMUTABLE" in IMMUTABLE_UNACCENT_SQL
    assert "'public.unaccent'::regdictionary" in IMMUTABLE_UNACCENT_SQL


def test_nothing_in_this_repository_installs_the_immutable_wrapper() -> None:
    """The module claims the wrapper is written down and not installed. This checks the claim.

    A claim about what is not built is the kind that rots first, because the day somebody does
    build it there is no reason for them to go back and correct a docstring. This fails on that
    day instead, which is when the sentence needs changing.

    Delete this and the module can go on saying nothing is installed long after something
    is."""
    migrations = REPO / "migrations"
    installed = [
        path
        for path in migrations.rglob("*.py")
        if "immutable_unaccent" in path.read_text(encoding="utf-8")
    ]

    assert installed == [], f"the wrapper is installed by {installed}, so the docstring is wrong"


# ------------------------------------------------- the minimum length (M14.2.5)
def test_a_three_letter_company_goes_to_a_person_and_a_four_letter_one_does_not() -> None:
    """IBM is a real company, so the guard routes rather than refuses, and it routes at four.

    The boundary is asserted with literal names of known length rather than with a string built
    from `MIN_KEY_CHARS`, which would move with the constant and be green for every value it
    could hold.

    Delete this and the minimum can be changed to three or to six with nothing failing, and
    either the estate's largest counterparties are matched on one trigram or every four-letter
    company goes to a human queue."""
    short = normalise_name("IBM")
    long_enough = normalise_name("ACME")

    assert short.verdict is NameVerdict.TOO_SHORT
    assert short.match_key is None, "so it cannot reach the cascade"
    assert long_enough.verdict is NameVerdict.USABLE
    assert long_enough.match_key == "acme"


def test_a_short_name_is_normalised_rather_than_discarded() -> None:
    """Routing to review is not refusing, and the reviewer needs the work already done.

    The key is computed, the observed form is kept, and the fold id is stamped, exactly as for
    a usable name. Only `match_key` differs.

    Delete this and the guard can start returning an empty result for a short name, which reads
    as safe and hands a reviewer a queue item with nothing in it."""
    short = normalise_name("  IBM  ")

    assert short.key == "ibm"
    assert short.observed == "  IBM  "
    assert short.fold == ACCENT_FOLD_ID


def test_the_minimum_length_is_the_length_a_trigram_measurement_needs() -> None:
    """Four is arithmetic, not taste, and this is where the arithmetic is written down.

    A key of n characters has n - 2 trigrams that are not built out of pg_trgm's padding, and a
    similarity over fewer than two of those is a coincidence rather than a measurement. So the
    minimum is the trigram figure plus two.

    Delete this and `MIN_KEY_CHARS` becomes a number with a comment, and the next person tuning
    the review queue's length lowers it because three is nearly four."""
    assert MIN_KEY_CHARS == MIN_TRIGRAMS_FOR_A_MEASUREMENT + 2


def test_a_name_with_no_letters_or_digits_in_it_has_no_key_at_all() -> None:
    """A field holding only punctuation is not a name, and it must not become a usable key.

    Distinct from the entirely-a-suffix case: there is nothing to fall back to, so the key is
    genuinely empty, and the whole of the protection is that `match_key` is None.

    Delete this and an empty key reaches the cascade, where it is equal to every other empty
    key."""
    for junk in ("---", "  ", ".", "\u200b"):
        result = normalise_name(junk)
        assert result.verdict is NameVerdict.NOTHING_LEFT, f"{junk!r}"
        assert result.match_key is None


def test_every_verdict_that_is_not_usable_routes_a_name_to_a_person() -> None:
    """One verdict admits a name to the cascade; the rest send it to a human.

    `ROUTES_TO_REVIEW` is written out in the module rather than derived as "everything except
    USABLE", so this checks a hand-written set against the vocabulary. Adding a fourth review
    verdict without deciding which side it falls on fails here.

    Delete this and a new verdict defaults to whatever `match_key` happens to do with it, which
    is to hand the cascade a key."""
    assert set(NameVerdict) - {NameVerdict.USABLE} == ROUTES_TO_REVIEW
    assert NameVerdict.USABLE not in ROUTES_TO_REVIEW

    for verdict in ROUTES_TO_REVIEW:
        assert verdict is not NameVerdict.USABLE


def test_normalisation_never_raises_on_anything_a_source_might_hold() -> None:
    """A backfill walks millions of rows and must not stop on the worst one.

    Every shape here exists in a real CRM export. Each gets a verdict and a sentence.

    Delete this and a `ValueError` for a blank name reads as defensive programming, and the
    first full backfill dies partway through with a stack trace naming a customer record."""
    for awful in ("", " ", "\u00a0", "?" * 500, "123", "\u4e2d\u6587", "Pte", "-"):
        result = normalise_name(awful)
        assert result.reason, f"{awful!r} produced no explanation"
        assert isinstance(result.verdict, NameVerdict)


# -------------------------------------------------------- Singapore UEN (M14.2.6)
def test_the_three_published_uen_formats_are_accepted() -> None:
    """The positive case, without which every refusal test below is met by refusing everything.

    One of each documented shape: eight digits and a letter for a business, a year and five
    digits and a letter for a local company, and a century prefix, two year digits, an
    entity-type code, four digits and a letter for the other agencies.

    Delete this and `check_uen` can start returning invalid for every input and the rest of
    this section stays green."""
    business = check_uen("53001234B")
    local = check_uen("201912345A")
    other = check_uen("T09LL0001B")

    assert (business.valid, business.kind) == (True, UenKind.BUSINESS)
    assert (local.valid, local.kind) == (True, UenKind.LOCAL_COMPANY)
    assert (other.valid, other.kind) == (True, UenKind.OTHER)


def test_a_uen_has_exactly_one_spelling() -> None:
    """Case and surrounding whitespace are accepted; the canonical form is what comes back.

    `canonical.identifier_hash` normalises nothing on purpose, so two spellings of one
    registration number reaching it produce two digests that never join. This function is where
    the one spelling is decided.

    Delete this and a lower-case UEN from one connector and an upper-case one from another
    become two hard identifiers for one company, which is a miss nothing reports."""
    assert check_uen(" t09ll0001b ").canonical == "T09LL0001B"
    assert check_uen("53001234b").canonical == "53001234B"


def test_a_reformatted_uen_is_refused_rather_than_repaired() -> None:
    """A hyphen in the middle is somebody's formatting, and stripping it would invent a value.

    Accepting "2019-12345A" means accepting that a UEN has more than one written form, and the
    next source writes it with spaces. Refusing sends it to the review path with the original
    intact.

    Delete this and a separator-stripping "helpful" branch appears, and the value that gets
    hashed is one no register ever issued."""
    assert not check_uen("2019-12345A").valid
    assert not check_uen("530 012 34B").valid
    assert check_uen("2019-12345A").canonical == "", "and nothing invalid carries a spelling"


def test_a_uen_of_the_wrong_length_is_refused() -> None:
    """Length is the first thing that separates the three formats, so it is checked exactly.

    Nine and ten are the only lengths any format has, so eight and eleven are refused
    outright. The case that matters more is "53001234BX": ten characters, which is a real UEN
    length, and a valid business UEN with a letter appended. Only the closing anchor refuses
    it, and a pattern that has lost one accepts it by matching the prefix and reports it as a
    business UEN.

    Delete this and `^[0-9]{8}[A-Z]` without its `$` passes every other test in this file, and
    a registration number with a character too many reaches the stage of the cascade that
    merges two companies on one identifier."""
    for wrong in ("5300123B", "5300123456B", "T09LL00001B", "T09LL001B"):
        assert not check_uen(wrong).valid, f"{wrong} was accepted"

    for appended in ("53001234BX", "201912345AB", "T09LL0001BB"):
        assert not check_uen(appended).valid, f"{appended} was accepted by a prefix match"


def test_the_century_prefix_of_the_other_format_is_checked() -> None:
    """T, S and R are the published prefixes and nothing else is one.

    The positive half is in the acceptance test above; this is the negative, and it is the
    character-class check that a lazy pattern would write as a letter.

    Delete this and `^[A-Z][0-9]{2}...` reads as tidier and accepts a value from a source that
    has invented its own scheme."""
    assert check_uen("T09LL0001B").valid
    assert check_uen("S98FC1234X").valid
    assert check_uen("R00CS9999Z").valid
    assert not check_uen("X09LL0001B").valid
    assert not check_uen("109LL0001B").valid


def test_the_entity_type_code_is_checked_for_its_shape_and_not_against_a_list() -> None:
    """Deliberately permissive, and the reason is worth keeping in front of a reader.

    The two-letter codes are maintained by the agencies in the scheme and the set grows when
    one is added. An allowlist written today rejects the UEN of a body registered tomorrow, and
    a rejected UEN here is a real entity dropping out of stage one of the cascade quietly. So a
    code nobody has heard of is accepted structurally.

    Delete this and somebody adds the allowlist as an improvement, and the failure it causes is
    invisible for as long as it takes anybody to notice a client is not matching."""
    assert check_uen("T09ZZ0001B").valid, "an unfamiliar code is still structurally a UEN"
    assert not check_uen("T091L0001B").valid, "but a digit is not a letter"


def test_nothing_can_claim_the_check_character_was_verified() -> None:
    """**The claim this module refuses to let anybody make.**

    ACRA does not publish the check-digit algorithm. A `UenCheck` saying the check character
    was verified would tell a caller that a hard identifier had been validated when its last
    character was only checked for being a letter, and that caller is stage one of the cascade.

    Asserted by construction rather than by reading the default, because a default is a value
    somebody overrides.

    Delete this and the field becomes an ordinary boolean, somebody sets it while implementing
    a check-digit routine found on the internet, and the routine is one of the several that
    disagree."""
    with pytest.raises(ValueError, match="check character"):
        UenCheck(
            valid=True,
            kind=UenKind.BUSINESS,
            canonical="53001234B",
            reason="",
            check_character_verified=True,
        )

    assert check_uen("53001234B").check_character_verified is False
    assert check_uen("53001234B").format_verified is True


def test_an_incorporation_year_later_than_the_caller_s_clock_is_refused() -> None:
    """A transposed year passes every character-class check, so the ceiling is what catches it.

    2260 for 2026 is four digits in the right place. The ceiling is a parameter because this
    module reads no clock, and it is optional because a caller without one is better served by
    a weaker check than by a wrong one.

    Delete this and the year half of the local-company format is checked for being four digits
    and nothing else, which any five-digit sequence satisfies."""
    assert not check_uen("226012345A", year_ceiling=2026).valid
    assert check_uen("201912345A", year_ceiling=2026).valid, "and a real year still passes"
    assert check_uen("226012345A").valid, "with no ceiling given, the year is not judged"


def test_a_value_that_is_not_a_uen_carries_no_canonical_spelling() -> None:
    """An invalid result has an empty canonical form, so nothing downstream can hash it.

    The dataclass refuses the two inconsistent shapes as well: valid with no spelling, and
    invalid with one. Either would be a value something reaches for without reading `valid`.

    Delete this and a refusal that still carries the input becomes the thing a caller passes to
    `identifier_hash`."""
    assert check_uen("hello").canonical == ""

    with pytest.raises(ValueError, match="canonical"):
        UenCheck(valid=True, kind=UenKind.BUSINESS, canonical="", reason="")
    with pytest.raises(ValueError, match="canonical"):
        UenCheck(valid=False, kind=None, canonical="53001234B", reason="")


def test_a_uen_check_has_nowhere_to_put_anything_but_the_value_it_was_given() -> None:
    """The shape of the result, pinned so that a later field addition is a visible change.

    Six fields and no more: whether it is one, which kind, the one spelling, why, and the two
    flags saying what was and was not checked.

    Delete this and a `check_digit` field appears with a plausible default."""
    names = {one.name for one in dataclass_fields(UenCheck)}

    assert names == {
        "valid",
        "kind",
        "canonical",
        "reason",
        "format_verified",
        "check_character_verified",
    }


def test_the_suffix_set_and_the_collapse_agree_about_what_a_token_is() -> None:
    """Every legal form in the set survives `collapse` as one token.

    A member with a space, a full stop or a capital in it would never match anything, because
    the strip runs over collapsed tokens. That failure is silent: the set looks right, the
    strip looks right, and the entry does nothing.

    Delete this and "Pte. Ltd." can be added to the set as a convenience and quietly never
    fire."""
    for token in SUFFIX_TOKENS:
        assert collapse(token) == token, f"{token!r} is not what collapse produces"
        assert " " not in token
