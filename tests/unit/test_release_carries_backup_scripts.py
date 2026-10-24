"""The release archive carries the backup scripts and the restore drill.

Task ids: M42.7.4
"""

from __future__ import annotations

from pathlib import Path

from brain.deployment.release import REPO, archive_files, carried_paths, included_by, refused_by

BACKUP = REPO / "ops" / "backup"
DRILL_PAGE = REPO / "docs" / "install" / "restore-drill.md"


def _scripts() -> list[str]:
    return sorted(f"ops/backup/{one.name}" for one in BACKUP.iterdir() if one.is_file())


def test_every_file_in_ops_backup_is_included_and_none_is_refused() -> None:
    """The drill and the scripts it runs beside travel together. Delete this and a script added
    to the folder is left out of the archive, so a drill run on a server is run with a mix of
    releases."""
    scripts = _scripts()

    assert "ops/backup/brain-restore-drill" in scripts and len(scripts) >= 8
    for path in scripts:
        assert included_by(path), path
        assert not refused_by(path), path


def test_the_archive_this_tree_would_publish_contains_the_restore_drill() -> None:
    """Asked of the function that lists the archive, not of the rule. Delete this and a rule that
    matches on paper and selects nothing passes."""
    carried = set(carried_paths(REPO))

    assert set(_scripts()) <= carried
    assert set(_scripts()) <= set(archive_files(REPO))


def test_the_drill_page_no_longer_tells_a_person_to_fetch_the_script_by_hand() -> None:
    """The page says where the script is in the archive. Delete this and the page goes on telling
    a person to copy a script from a repository they may not have, from a tag they must guess."""
    text = DRILL_PAGE.read_text(encoding="utf-8")

    assert "does not carry" not in text
    assert "/opt/brain/ops/backup/brain-restore-drill" in text
    assert Path(BACKUP / "brain-restore-drill").is_file()
