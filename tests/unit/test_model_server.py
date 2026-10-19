"""The model server's sizing, its four settings and what a configuration asks of a host.

Three things in this file are worth reading before the rest, because each is the shape of test that
would be easy to write so that it proves nothing.

**The figures are never asserted against themselves.** `SIZING` says what each part holds, and a
test reading it back and comparing it with itself is green for every value it could hold. So the
limit is asserted through what makes it right: the largest part and not the sum, the mapped weights
counted in the container's limit and not in what the host must give, the largest document counted
for the parts that read one and not for those that do not, and the whole thing against the old
design's figure, which is a number from another file.

**No figure is a measurement, and a test says so.** A figure marked measured by somebody who did
not measure it is worse than an unmeasured one because it stops anybody asking.

**The settings are judged together.** One setting is saved at a time, and a limit is too small for
the parts chosen before it, so the test that matters saves them in both orders.

Task ids: M7.2.1, M7.2.3, M7.2.4, M7.3.3, M7.7.11, M32.2.1.2
"""

from __future__ import annotations

import pytest

from brain.knowledge.embed_queue import batch_budget_bytes
from brain.knowledge.ingest import TYPE_LIMITS, MediaType, ceiling_for
from brain.knowledge.parse_budget import MIB
from brain.ops.inference import weights_mib
from brain.ops.model_server import (
    AUTOMATIC,
    BASE_MIB,
    DEFAULT_IDLE_SECONDS,
    DEFAULT_UPLOAD_MB,
    DOCUMENT_PARTS,
    IDLE_BOUNDS,
    ROUND_MIB,
    SETTINGS,
    SIZING,
    UPLOAD_BOUNDS,
    ModelServerConfig,
    ModelServerError,
    Part,
    PartSizing,
    anonymous_peak_mib,
    config_from,
    effective_limit_mib,
    environment,
    limit_problem,
    non_reclaimable_mib,
    part_peak_mib,
    parts_from,
    read_config,
    request_ceiling_bytes,
    request_working_mib,
    requirement,
    rounded_up,
    setting_problem,
    suggested_limit_mib,
    upload_working_mib,
)

EVERYTHING = "embedding,layout,ocr,tika,entities"


def test_every_part_has_a_row_and_a_stated_origin_for_its_figures() -> None:
    """The table is total over `Part`, so a part added without a row is a refusal at import and not
    a `KeyError` inside a memory calculation, and every row says where its figures came from.

    Delete this and a part can be switched on that nothing sized, and the limit a person is shown
    for it is whatever the largest other part happens to be."""
    assert set(SIZING) == set(Part)
    for part, row in SIZING.items():
        assert row.part is part
        assert row.basis.strip(), part


def test_no_figure_in_the_table_has_been_measured() -> None:
    """A statement of fact today, and the test is what has to be edited when it stops being one:
    there is no server, no weights and no image on the host these were written on. The measured
    figures live in `ops.model_server_peak` and replace a judgement by a row, never by an edit here.

    Delete this and a figure can be marked measured by somebody who did not measure it, which is
    worse than an unmeasured figure because it stops anybody asking."""
    assert [row.part.value for row in SIZING.values() if row.measured] == []


def test_a_part_that_does_not_say_where_its_figures_came_from_cannot_be_declared() -> None:
    """The shape `brain.ops.inference.ServedModel` has. A number in a memory budget is an assertion
    about a machine, and one whose origin nobody wrote down cannot be checked.

    Delete this and the table becomes a list of integers somebody typed once."""
    with pytest.raises(ModelServerError, match="does not say where"):
        PartSizing(
            part=Part.OCR,
            engine="e",
            model="m",
            quantisation="q",
            anonymous_mib=1,
            mapped_mib=0,
            basis="  ",
        )
    with pytest.raises(ModelServerError, match="cannot give back"):
        PartSizing(
            part=Part.OCR,
            engine="e",
            model="m",
            quantisation="q",
            anonymous_mib=0,
            mapped_mib=0,
            basis="a basis",
        )


# ------------------------------------------------------------------ one part at a time
def test_the_limit_is_the_largest_part_and_never_the_sum_of_them() -> None:
    """The design in one assertion. Item 120 sized the sum, and the sum is what an install pays for
    if every part is loaded together. Here the container loads one at a time, so choosing all five
    costs the largest and not their total.

    Asserted against the old design's figure, which is a number from another file: the sum of the
    five parts' own peaks is far over what the container is given, and it is given the largest.

    Delete this and `requirement` can be changed to add the parts up, which is the 3,072 MiB
    container item 120 found would not fit, with every other test here still green."""
    config = config_from(parts=EVERYTHING)
    by_part = {one: part_peak_mib(one, config.upload_mb) for one in config.parts}

    assert requirement(config).limit_mib == rounded_up(max(by_part.values()))
    assert requirement(config).limit_mib < sum(by_part.values())
    assert requirement(config).largest is max(by_part, key=lambda one: by_part[one])


def test_choosing_more_parts_never_asks_for_less_and_a_smaller_part_asks_for_nothing_extra() -> (
    None
):
    """Monotone in the right way: adding a part to the choice cannot lower the limit, and adding a
    part smaller than the largest already chosen leaves it where it was.

    Delete this and a limit can be computed from the last part named, so the order a person types
    the parts in decides how much memory they are given."""
    layout = effective_limit_mib(config_from(parts="layout"))
    assert effective_limit_mib(config_from(parts="layout,embedding")) == layout
    assert effective_limit_mib(config_from(parts="embedding,layout")) == layout
    assert effective_limit_mib(config_from(parts="embedding")) < layout
    assert effective_limit_mib(config_from(parts="entities,layout")) >= layout


def test_the_default_choice_is_a_fraction_of_what_item_120_sized() -> None:
    """The point of the work, asserted against a figure from outside this module: item 120 sized
    the server at 3,072 MiB with three models resident, and the default choice, the embedding part
    alone, is under half of that. All five parts together are under half of it too, because only
    one is resident.

    Delete this and the saving over the rejected design stops being something a test would notice
    losing."""
    assert effective_limit_mib(config_from()) < 3072 // 2
    assert effective_limit_mib(config_from(parts=EVERYTHING)) < 3072 // 2 + 256
    assert weights_mib() + 512 > 3072 // 2, "the rejected design's own sum, for the comparison"


def test_a_larger_document_costs_the_parts_that_read_one_and_nothing_else() -> None:
    """The upload size sizes the parts that are sent a document and not the ones sent text. An
    embedding part told it may be handed a 100 MB file would be sized for memory it is never asked
    to hold.

    Delete this and the upload setting raises the limit of an install that reads no documents."""
    small, large = DEFAULT_UPLOAD_MB, DEFAULT_UPLOAD_MB * 3
    for part in DOCUMENT_PARTS:
        assert anonymous_peak_mib(part, large) > anonymous_peak_mib(part, small), part
    for part in set(Part) - DOCUMENT_PARTS:
        assert anonymous_peak_mib(part, large) == anonymous_peak_mib(part, small), part
    # And a request body is charged to the part that is sent text and to nobody else: three copies
    # of the largest batch for embedding, nothing for the layout, scanned-page, general or entity
    # parts, which are sized by a document or by a passage.
    assert request_working_mib(Part.EMBEDDING) == -(-3 * batch_budget_bytes() // MIB)
    assert [request_working_mib(one) for one in Part if one is not Part.EMBEDDING] == [0, 0, 0, 0]


def test_the_scanned_page_reader_is_not_sized_for_an_image_the_door_never_admits() -> None:
    """The working set is the smaller of the install's limit and the type's own ceiling, times that
    container's expansion. Images stop at the door's ceiling for them, so raising the install's
    limit past it does not raise what the scanned-page reader needs for an image.

    Delete this and the reader is sized for a 100 MB photograph the door refuses at 10."""
    image_ceiling = max(ceiling_for(MediaType.PNG), ceiling_for(MediaType.JPEG))
    pdf_ceiling = ceiling_for(MediaType.PDF)
    assert image_ceiling < pdf_ceiling < 100 * MIB

    # With the install's limit far above every ceiling, each type is held to its own: a PDF at
    # 50 MiB and six times (the door's ceiling and the expansion table, both from other files), an
    # image at its ceiling and sixteen or twenty times. The largest of them is the figure.
    expected = max(
        min(100 * MIB, ceiling_for(media_type)) * expansion
        for media_type, expansion in (
            (MediaType.PDF, 6),
            (MediaType.PNG, 16),
            (MediaType.JPEG, 20),
        )
    )
    assert upload_working_mib(Part.OCR, 100) == -(-expected // MIB)
    # And a limit below every ceiling is the limit itself, times the worst expansion: 20 for a JPEG.
    assert upload_working_mib(Part.OCR, 1) == 20
    assert TYPE_LIMITS[MediaType.JPEG].max_bytes < 100 * MIB


# ------------------------------------------------------------------ the kernel's cache
def test_mapped_weights_are_in_the_containers_limit_and_not_in_what_the_host_must_give() -> None:
    """The cache rule in numbers. The embedding model's file is mapped, so its pages are charged to
    the container and the kernel can give them back: the container's limit has to cover them and the
    host's non-reclaimable figure has to leave them out. Both halves, because a test of only one is
    satisfied by a design that counts the cache twice or never.

    Delete this and the model's 640 MiB is either left out of the limit, so the part is read back
    from disk for every request, or left in what the host must have spare, so the owner's server
    looks full while it holds gigabytes of cache it would hand over."""
    mapped = SIZING[Part.EMBEDDING].mapped_mib
    config = config_from()

    assert mapped >= 600
    assert requirement(config).limit_mib >= BASE_MIB + mapped + SIZING[Part.EMBEDDING].anonymous_mib
    assert requirement(config).non_reclaimable_mib == non_reclaimable_mib(
        Part.EMBEDDING, config.upload_mb
    )
    assert requirement(config).non_reclaimable_mib <= requirement(config).limit_mib - mapped


def test_the_host_is_asked_for_each_part_alone_so_a_small_part_is_not_refused_for_a_big_one() -> (
    None
):
    """One need per part in the environment, so the supervisor admits the embedding part on a host
    that could not hold the layout part it never asked for.

    Delete this and the admission check is one figure for the largest part, and an install that
    chose both is refused the smaller whenever the host cannot hold the larger."""
    variables = dict(environment(config_from(parts="embedding,layout")))

    assert int(variables["INFERENCE_NEED_EMBEDDING_MIB"]) < int(
        variables["INFERENCE_NEED_LAYOUT_MIB"]
    )
    assert {name for name in variables if name.startswith("INFERENCE_NEED_")} == {
        f"INFERENCE_NEED_{one.value.upper()}_MIB" for one in Part
    }


# ------------------------------------------------------------------ the four settings
def test_the_defaults_are_the_ones_the_owner_decided() -> None:
    """The upload size is 25, decided on 2026-10-05 (`docs/needs-rupash.md` item 119, the
    recommendation of 25 MB for every document type), and nothing here decides it again. The idle
    time is inside its own bounds and the memory is worked out.

    Delete this and the decided figure becomes whatever somebody types into the module."""
    assert DEFAULT_UPLOAD_MB == 25
    assert IDLE_BOUNDS[0] <= DEFAULT_IDLE_SECONDS <= IDLE_BOUNDS[1]
    config = read_config(env={}, saved={})
    assert config == ModelServerConfig()
    assert config.parts == (Part.EMBEDDING,)
    assert config.memory_override_mib is None


def test_every_setting_the_module_reads_is_declared_with_the_default_it_reads() -> None:
    """The four names are declared in `brain.install`, and a name read that is not declared is a
    refusal there. The default text each carries is the one `config_from` uses.

    Delete this and a setting can be renamed in one place, so the screen saves a value nothing
    reads."""
    from brain.install import BY_NAME

    assert set(SETTINGS) <= set(BY_NAME)
    assert BY_NAME["INSTALL_MODEL_UPLOAD_MB"].default == str(DEFAULT_UPLOAD_MB)
    assert BY_NAME["INSTALL_MODEL_IDLE_SECONDS"].default == str(DEFAULT_IDLE_SECONDS)
    assert BY_NAME["INSTALL_MODEL_MEMORY_MIB"].default == AUTOMATIC


@pytest.mark.parametrize(
    "text", ["", "  ", "nonsense", "embedding,nonsense", "layout, ,gliner"], ids=repr
)
def test_a_list_of_parts_naming_nothing_or_naming_a_stranger_is_refused_in_words(text: str) -> None:
    """A typo that chose nothing would read on the server as a part that failed to load and in the
    setting as one that runs. Delete this and the typo is the second."""
    with pytest.raises(ModelServerError, match="part"):
        parts_from(text)


def test_parts_are_read_in_the_order_written_and_a_part_named_twice_is_refused() -> None:
    """Order is the person's and is kept; naming a part twice is a slip and is refused rather than
    quietly collapsed. Delete this and a duplicate doubles nothing today and something tomorrow."""
    assert parts_from("ocr, embedding") == (Part.OCR, Part.EMBEDDING)
    assert parts_from("EMBEDDING") == (Part.EMBEDDING,)
    with pytest.raises(ModelServerError, match="twice"):
        config_from(parts="ocr,ocr")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idle", str(IDLE_BOUNDS[0] - 1)),
        ("idle", str(IDLE_BOUNDS[1] + 1)),
        ("idle", "soon"),
        ("upload", str(UPLOAD_BOUNDS[0] - 1)),
        ("upload", str(UPLOAD_BOUNDS[1] + 1)),
        ("upload", "big"),
        ("memory", str(BASE_MIB - 1)),
        ("memory", "lots"),
    ],
)
def test_a_figure_outside_its_bounds_or_not_a_number_is_refused(field: str, value: str) -> None:
    """Both ends of both bounds, and the not-a-number case, so the refusal is seen to fire from
    each side. An idle time of nought would be a part held for ever and one of a second would load
    between every two requests. Delete this and a bound can be widened with nothing noticing."""
    with pytest.raises(ModelServerError):
        config_from(**{field: value})


def test_a_figure_at_each_bound_is_accepted() -> None:
    """The positive half of the bounds test, so a check that refuses everything is caught.

    Delete this and the bounds can be tightened until only the default passes."""
    config_from(idle=str(IDLE_BOUNDS[0]), upload=str(UPLOAD_BOUNDS[0]))
    config_from(idle=str(IDLE_BOUNDS[1]), upload=str(UPLOAD_BOUNDS[1]), memory=str(BASE_MIB))


def test_a_limit_set_by_hand_is_refused_under_the_parts_chosen_and_accepted_at_or_over_it() -> None:
    """Under is refused and over is not: a larger limit wastes memory the plan will say it spends,
    and a smaller one is a part killed on its first large request. The sentence names the figure
    that would do, so a person can act on it.

    Delete this and a limit can be typed under what the part needs, which starts and fails on the
    first large document."""
    needed = requirement(config_from(parts="layout")).limit_mib

    assert limit_problem(config_from(parts="layout")) == ""
    assert limit_problem(config_from(parts="layout", memory=str(needed))) == ""
    assert limit_problem(config_from(parts="layout", memory=str(needed + 512))) == ""
    short = limit_problem(config_from(parts="layout", memory=str(needed - ROUND_MIB)))
    assert str(needed) in short
    assert "layout" in short


def test_an_override_is_the_limit_the_server_is_costed_and_started_at() -> None:
    """When a person sets a limit it is the figure the plan charges and the container gets, not
    the worked-out one. Delete this and the setting is accepted, shown on the screen and ignored."""
    needed = requirement(config_from()).limit_mib
    config = config_from(memory=str(needed + 256))

    assert effective_limit_mib(config) == needed + 256
    assert dict(environment(config))["INFERENCE_MEMORY_MIB"] == str(needed + 256)


def test_the_environment_the_server_is_started_with_is_numbers_and_one_comma_list() -> None:
    """The deploy step exports each of these through a shell without quoting, so none may carry a
    space, a quote, a dollar or a newline.

    Delete this and a value that can carry a character the shell reads becomes a command on the
    server."""
    for key, value in environment(config_from(parts=EVERYTHING)):
        assert key.startswith("INFERENCE_")
        assert value and all(c.isalnum() or c in ",_" for c in value), (key, value)


def test_a_limit_that_is_too_small_is_judged_against_the_parts_chosen_in_either_order() -> None:
    """One setting is saved at a time, so the same two values arrive in two orders. A limit set
    first is judged against the parts already chosen, and parts chosen after it against the limit.
    Both are refused with the same sentence and neither order lets the pair through.

    Delete this and the order a person saves two settings in decides whether the pair is checked."""
    current = {"INSTALL_MODEL_PARTS": "embedding", "INSTALL_MODEL_MEMORY_MIB": "1088"}

    assert setting_problem("INSTALL_MODEL_PARTS", "embedding", current=current) == ""
    assert "layout" in setting_problem("INSTALL_MODEL_PARTS", "layout", current=current)
    assert (
        setting_problem(
            "INSTALL_MODEL_MEMORY_MIB",
            "1088",
            current={"INSTALL_MODEL_PARTS": "layout", "INSTALL_MODEL_MEMORY_MIB": "auto"},
        )
        != ""
    )
    assert (
        setting_problem(
            "INSTALL_MODEL_MEMORY_MIB",
            "auto",
            current={"INSTALL_MODEL_PARTS": "layout", "INSTALL_MODEL_MEMORY_MIB": "1088"},
        )
        == ""
    )


def test_a_name_that_is_not_one_of_the_four_settings_is_refused_by_the_judge() -> None:
    """The judge is asked about exactly the four. Delete this and any name is judged as if it were
    one of them, so a typo in the route is a silent pass."""
    with pytest.raises(ModelServerError):
        setting_problem("INSTALL_SERVICES", "none")


# ------------------------------------------------------------------ the request ceiling
def test_the_ceiling_is_the_larger_of_a_document_and_a_batch_and_a_whole_number_of_mebibytes() -> (
    None
):
    """The two things the server is sent, each sized for what it is: a document, base64 encoded,
    and an embedding batch up to the slot's budget. Whole mebibytes so the figure in a compose file
    is one a person can read.

    Delete this and the ceiling is the batch budget for an install that reads documents, and every
    document over it is refused after it has been fetched, scanned and stored."""
    documents = request_ceiling_bytes(config_from(parts="layout"))
    batches = request_ceiling_bytes(config_from(parts="embedding"))

    assert documents >= ((DEFAULT_UPLOAD_MB * MIB + 2) // 3) * 4
    assert batches >= batch_budget_bytes()
    # An install that reads no documents is not given a document-sized ceiling: its embedding
    # batches are the largest thing it is sent, and a larger ceiling is memory it is never asked
    # to hold. Whole mebibytes of the batch budget, and not a byte more.
    assert batches == -(-batch_budget_bytes() // MIB) * MIB
    assert request_ceiling_bytes(config_from(parts="entities")) == MIB
    assert documents % MIB == 0 and batches % MIB == 0
    assert request_ceiling_bytes(config_from(parts="embedding,layout")) == max(documents, batches)


# ------------------------------------------------------------------ the suggestion
def test_nothing_measured_suggests_nothing_and_the_largest_peak_suggests_a_limit_over_it() -> None:
    """A suggestion is made from what ran and never invented: no peaks is no figure. With peaks it
    is the largest, with a margin, in whole steps, and never lower than the peak itself.

    Delete this and a limit is suggested from an average, which is right until the day it is not,
    or from nothing, which is a made-up number."""
    assert suggested_limit_mib([]) is None
    suggestion = suggested_limit_mib([700, 910, 820])

    assert suggestion is not None
    assert suggestion >= 910
    assert suggestion % ROUND_MIB == 0
    assert suggestion == suggested_limit_mib([910])
    larger = suggested_limit_mib([910, 1000])
    assert larger is not None and larger > suggestion


def test_rounding_goes_up_and_never_down() -> None:
    """A limit rounded down is a limit under what was asked. Delete this and a figure at a step
    boundary plus one comes out a step short."""
    assert rounded_up(ROUND_MIB) == ROUND_MIB
    assert rounded_up(ROUND_MIB + 1) == 2 * ROUND_MIB
    assert rounded_up(1) == ROUND_MIB
