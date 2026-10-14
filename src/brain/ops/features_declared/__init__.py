"""Where a new feature switch is declared: one module each, found by listing this directory.

**A feature is declared by adding a file here, and nothing else in this repository lists it.**
`brain.ops.features.FEATURES` is the built-in list followed by every public `Feature` bound at the
top level of each module in this package, modules in name order (`declared_in`). Until 2026-10-14
a feature was a constant appended above the tuple and a line appended inside it, both at the end
of `features.py`, so two pull requests that each added a feature conflicted in two places, and a
conflicted pull request gets no CI: thirty to sixty minutes each time. A new file cannot conflict
with another new file, and the two files are still read together when the list is assembled.

A module here looks like this, and its `read_by` readers import the feature from it:

    from brain.ops.feature_model import Feature

    BROWSER_RUNS: Final = Feature(name="browser_runs", title=..., what=..., while_off=...,
                                  read_by=("brain.browsing.driver:browser_runs_are_on",))

**The reader check still holds.** `brain.ops.features.feature_gaps` finds the constant's name in
these modules as well as in `features.py`, so a declared reader that stops asking, and a function
that asks about a feature nobody named it a reader of, are findings here as they are there.

**Why name order, and why a directory rather than a registration call.** The order the screen
lists features must not depend on import order or on which pull request merged first, so it is the
file names sorted. A `register(FEATURE)` call at the bottom of each module was rejected: it runs
only if something imports the module, which is the defect this repository keeps finding (a
declaration nothing reaches), where listing the directory reaches every file in it by
construction.

A module whose name starts with an underscore is a helper and is not read as a declaration.

Task ids: M27.15.51
"""
