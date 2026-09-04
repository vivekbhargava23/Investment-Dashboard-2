from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "file.sh"


def _run(
    *args: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _ticket() -> str:
    padding = "This sentence makes the ticket body substantial and testable. " * 12
    return f"""# TICKET-TEST-1 — Filing workflow regression

**Priority:** HIGH
**Milestone:** Investment Panel
**Depends on:** none.

## Problem
The filing workflow must be safe to resume after a partial external failure.

## Acceptance criteria
- [ ] Existing issues and board cards are reused.
- [ ] Ambiguous duplicate issues stop before side effects.
- [ ] Related planning documents are committed only when explicitly listed.

## Notes
{padding}
"""


def _fake_gh(bin_dir: Path) -> Path:
    path = bin_dir / "gh"
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
log = Path(os.environ["FAKE_GH_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\\n")

mode = os.environ.get("FAKE_ISSUE_MODE", "none")
url = "https://github.com/example/repo/issues/42"

if args[:2] == ["issue", "list"]:
    rows = []
    if mode in {"existing", "duplicate"}:
        rows.append({
            "number": 42,
            "title": "TICKET-TEST-1 — Existing",
            "state": "OPEN",
            "url": url,
        })
    if mode == "duplicate":
        rows.append({
            "number": 43,
            "title": "TICKET-TEST-1 — Duplicate",
            "state": "OPEN",
            "url": url.replace("42", "43"),
        })
    if mode == "closed":
        rows.append({
            "number": 41,
            "title": "TICKET-TEST-1 — Closed",
            "state": "CLOSED",
            "url": url.replace("42", "41"),
        })
    for row in rows:
        print(json.dumps(row))
elif args[:2] == ["project", "list"]:
    print(json.dumps({"projects": [{"number": 2, "id": "PROJECT"}]}))
elif args[:2] == ["project", "field-list"]:
    print(json.dumps({
        "fields": [{
            "name": "Status",
            "id": "STATUS",
            "options": [{"name": "Backlog", "id": "BACKLOG"}],
        }],
    }))
elif args[:2] == ["issue", "edit"]:
    print(url)
elif args[:2] == ["issue", "create"]:
    print(url)
elif args[:2] == ["project", "item-list"]:
    items = []
    if os.environ.get("FAKE_BOARD_ITEM") == "1":
        items.append({"id": "ITEM", "content": {"url": url}})
    print(json.dumps({"items": items}))
elif args[:2] == ["project", "item-add"]:
    print(json.dumps({"id": "ITEM"}))
elif args[:2] == ["project", "item-edit"]:
    print("{}")
elif args and args[0] == "api" and "milestones?state=all" in " ".join(args):
    print("open")
elif args[:2] == ["api", "graphql"]:
    if any("query($projectId" in arg for arg in args):
        print(json.dumps({"data": {"node": {"items": {"nodes": []}}}}))
    else:
        print("{}")
else:
    raise SystemExit(f"unexpected gh call: {args}")
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _repo(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    repo = tmp_path / "repo"
    origin = tmp_path / "origin.git"
    bin_dir = tmp_path / "bin"
    repo.mkdir()
    bin_dir.mkdir()
    _fake_gh(bin_dir)

    assert _run("git", "init", "--bare", str(origin), cwd=tmp_path).returncode == 0
    assert _run("git", "init", "-b", "main", cwd=repo).returncode == 0
    assert _run("git", "config", "user.name", "Test", cwd=repo).returncode == 0
    assert _run("git", "config", "user.email", "test@example.com", cwd=repo).returncode == 0

    (repo / "tools").mkdir()
    (repo / "docs" / "TICKETS").mkdir(parents=True)
    shutil.copy2(SCRIPT, repo / "tools" / "file.sh")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    assert _run("git", "add", ".", cwd=repo).returncode == 0
    assert _run("git", "commit", "-m", "fixture", cwd=repo).returncode == 0
    assert _run("git", "remote", "add", "origin", str(origin), cwd=repo).returncode == 0
    assert _run("git", "push", "-u", "origin", "main", cwd=repo).returncode == 0

    log = tmp_path / "gh.log"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GH_LOG"] = str(log)
    return repo, env, log


def _calls(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_unlisted_design_file_aborts_before_github_side_effects(tmp_path: Path) -> None:
    repo, env, log = _repo(tmp_path)
    (repo / "docs" / "TICKETS" / "TICKET-TEST-1-regression.md").write_text(
        _ticket(), encoding="utf-8"
    )
    design = repo / "docs" / "DESIGN" / "plan.md"
    design.parent.mkdir()
    design.write_text("# Plan\n", encoding="utf-8")

    result = _run("bash", "tools/file.sh", cwd=repo, env=env)

    assert result.returncode != 0
    assert "outside the explicit filing bundle" in result.stdout
    assert _calls(log) == []


def test_duplicate_open_issues_abort_before_create_or_board_changes(tmp_path: Path) -> None:
    repo, env, log = _repo(tmp_path)
    (repo / "docs" / "TICKETS" / "TICKET-TEST-1-regression.md").write_text(
        _ticket(), encoding="utf-8"
    )
    env["FAKE_ISSUE_MODE"] = "duplicate"

    result = _run("bash", "tools/file.sh", cwd=repo, env=env)
    calls = _calls(log)

    assert result.returncode != 0
    assert "has 2 open issues" in result.stdout
    assert not any(call[:2] == ["issue", "create"] for call in calls)
    assert not any(call[:2] == ["project", "item-add"] for call in calls)


def test_existing_issue_and_board_card_are_reused_and_bundle_is_committed(tmp_path: Path) -> None:
    repo, env, log = _repo(tmp_path)
    ticket = repo / "docs" / "TICKETS" / "TICKET-TEST-1-regression.md"
    ticket.write_text(_ticket(), encoding="utf-8")
    design = repo / "docs" / "DESIGN" / "plan.md"
    design.parent.mkdir()
    design.write_text("# Plan\n", encoding="utf-8")
    env["FAKE_ISSUE_MODE"] = "existing"
    env["FAKE_BOARD_ITEM"] = "1"

    result = _run(
        "bash",
        "tools/file.sh",
        "docs/DESIGN/plan.md",
        cwd=repo,
        env=env,
    )
    calls = _calls(log)

    assert result.returncode == 0, result.stdout + result.stderr
    assert any(call[:2] == ["issue", "edit"] for call in calls)
    assert not any(call[:2] == ["issue", "create"] for call in calls)
    assert not any(call[:2] == ["project", "item-add"] for call in calls)
    committed = _run("git", "show", "--name-only", "--format=", "HEAD", cwd=repo)
    assert "docs/TICKETS/TICKET-TEST-1-regression.md" in committed.stdout
    assert "docs/DESIGN/plan.md" in committed.stdout
