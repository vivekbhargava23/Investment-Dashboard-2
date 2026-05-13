"""Tests for tools/draft_ticket.sh branch guard and clean-tree guard.

Uses subprocess to invoke the script against a real temp git repo so the
bash guards run in their natural environment (no bats required).
"""
import subprocess
import textwrap
from pathlib import Path

SPEC = textwrap.dedent("""\
    ID: TICKET-999
    TITLE: Test ticket
    MILESTONE: Foundation
    PRIORITY: HIGH
    ESTIMATE: 1 hr
    NEXT_UP: false
    ---
    # TICKET-999 — Test ticket

    **Status:** QUEUED
""")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _setup_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo that looks enough like the real one."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")

    # Create minimal structure needed by the script before branch/tree guards
    (repo / "tools").mkdir()
    script_src = Path(__file__).parent.parent.parent.parent / "tools" / "draft_ticket.sh"
    (repo / "tools" / "draft_ticket.sh").write_bytes(script_src.read_bytes())

    (repo / "docs").mkdir()
    (repo / "docs" / "TICKETS").mkdir()
    (repo / "docs" / "TICKETS" / "BACKLOG.md").write_text("# BACKLOG\n")
    (repo / "docs" / "PROJECT_STATE.md").write_text("# STATE\n")

    # Initial commit so HEAD exists and we're on main
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo


def _run_script(repo: Path, stdin: str = SPEC) -> subprocess.CompletedProcess:  # type: ignore[type-arg]
    return subprocess.run(
        ["bash", "tools/draft_ticket.sh"],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(repo),
    )


# ---------------------------------------------------------------------------
# Branch guard
# ---------------------------------------------------------------------------

def test_branch_guard_fails_on_non_main(tmp_path: Path) -> None:
    repo = _setup_git_repo(tmp_path)
    _git(repo, "checkout", "-b", "feature-branch")

    result = _run_script(repo)

    assert result.returncode == 1
    assert "must be run from main" in result.stderr
    assert "feature-branch" in result.stderr


def test_branch_guard_passes_on_main(tmp_path: Path) -> None:
    repo = _setup_git_repo(tmp_path)
    # Should not fail on the branch guard (may fail later, but not on branch check)
    result = _run_script(repo)
    # The script will fail further down (sync_state.py not present in minimal repo),
    # but exit with a message other than the branch guard message
    assert "must be run from main" not in result.stderr


# ---------------------------------------------------------------------------
# Clean-tree guard
# ---------------------------------------------------------------------------

def test_clean_tree_guard_fails_with_dirty_tree(tmp_path: Path) -> None:
    repo = _setup_git_repo(tmp_path)
    # Create an uncommitted file
    (repo / "dirty_file.txt").write_text("untracked")

    result = _run_script(repo)

    assert result.returncode == 1
    assert "working tree is dirty" in result.stderr


# ---------------------------------------------------------------------------
# Guards fire before any file is written
# ---------------------------------------------------------------------------

def test_branch_guard_writes_no_files(tmp_path: Path) -> None:
    repo = _setup_git_repo(tmp_path)
    _git(repo, "checkout", "-b", "some-branch")

    tickets_before = set((repo / "docs" / "TICKETS").iterdir())
    _run_script(repo)
    tickets_after = set((repo / "docs" / "TICKETS").iterdir())

    assert tickets_before == tickets_after, "Branch guard must not create ticket files"


def test_clean_tree_guard_writes_no_files(tmp_path: Path) -> None:
    repo = _setup_git_repo(tmp_path)
    (repo / "dirty_file.txt").write_text("untracked")

    tickets_before = set((repo / "docs" / "TICKETS").iterdir())
    _run_script(repo)
    tickets_after = set((repo / "docs" / "TICKETS").iterdir())

    assert tickets_before == tickets_after, "Clean-tree guard must not create ticket files"
