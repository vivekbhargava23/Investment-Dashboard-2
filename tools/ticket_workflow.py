#!/usr/bin/env python3
"""Workflow helpers behind the agent ritual shell entry points."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_NUMBER = "2"
PROJECT_OWNER = "@me"

ACTIVE_STATUSES = {"Ready", "Backlog", "In progress", "In review"}
NEXT_STATUSES = {"Ready", "Backlog"}
DONE_STATUSES = {"Done"}
PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

_FULL_TICKET_RE = re.compile(r"\bTICKET-([A-Z0-9][A-Z0-9-]*)\b")
_BARE_TICKET_RE = re.compile(r"\b([A-Z]+(?:-[A-Z]+)*-?[0-9]+[A-Z0-9-]*)\b")
_FIELD_RE_TEMPLATE = r"^\*\*{name}:\*\*\s*(?P<value>.+?)\s*$"
_HEADING_RE = re.compile(r"^#\s+(TICKET-[A-Z0-9-]+)\s+(?:\u2014|-)\s+(.+?)\s*$")


@dataclass(frozen=True)
class TicketEntry:
    ticket_id: str
    issue_number: int
    issue_title: str
    title: str
    status: str
    priority: str
    model: str
    dependencies: tuple[str, ...]
    board_index: int
    ticket_file: Path | None = None
    issue_state: str | None = None


def repo_root() -> Path:
    return Path(run(["git", "rev-parse", "--show-toplevel"], capture=True).strip())


def run(command: Sequence[str], *, capture: bool = False, check: bool = True) -> str:
    kwargs: dict[str, Any] = {"text": True, "check": check}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    completed = subprocess.run(command, **kwargs)
    if capture:
        return completed.stdout
    return ""


def normalize_ticket_id(value: str) -> str:
    cleaned = value.strip().upper()
    cleaned = cleaned.replace(" ", "")
    if cleaned.startswith("TICKET-"):
        return cleaned
    return f"TICKET-{cleaned}"


def compact_ticket_id(ticket_id: str) -> str:
    return ticket_id.removeprefix("TICKET-")


def parse_heading(body: str) -> tuple[str | None, str | None]:
    for line in body.splitlines():
        if not line.strip():
            continue
        match = _HEADING_RE.match(line)
        if match:
            return match.group(1), match.group(2)
        return None, None
    return None, None


def parse_field(body: str, field_name: str) -> str | None:
    pattern = re.compile(
        _FIELD_RE_TEMPLATE.format(name=re.escape(field_name)),
        flags=re.MULTILINE,
    )
    match = pattern.search(body)
    if match is None:
        return None
    return match.group("value").strip()


def parse_priority(body: str) -> str:
    value = parse_field(body, "Priority")
    if value is None:
        return "LOW"
    priority = value.split()[0].strip().upper()
    return priority if priority in PRIORITY_ORDER else "LOW"


def parse_model(body: str) -> str:
    value = parse_field(body, "Recommended model")
    if value is None:
        return "?"
    return re.split(r"\s+[\u2014-]\s+", value, maxsplit=1)[0].strip() or "?"


def parse_dependencies(body: str) -> tuple[str, ...]:
    raw = parse_field(body, "Depends on")
    if raw is None:
        raw = parse_field(body, "Dependencies")
    if raw is None:
        return ()

    normalized = raw.strip()
    if normalized in {"", "-", "\u2014", "None", "none", "N/A", "n/a"}:
        return ()

    seen: set[str] = set()
    dependencies: list[str] = []
    for match in _FULL_TICKET_RE.finditer(normalized):
        ticket_id = normalize_ticket_id(match.group(0))
        if ticket_id not in seen:
            seen.add(ticket_id)
            dependencies.append(ticket_id)

    without_full_ids = _FULL_TICKET_RE.sub(" ", normalized)
    for match in _BARE_TICKET_RE.finditer(without_full_ids):
        token = match.group(1)
        if token in {"ADR-010", "ADR-011", "ADR-012"}:
            continue
        ticket_id = normalize_ticket_id(token)
        if ticket_id not in seen:
            seen.add(ticket_id)
            dependencies.append(ticket_id)
    return tuple(dependencies)


def title_from_issue_title(issue_title: str) -> tuple[str | None, str]:
    match = re.match(r"^(TICKET-[A-Z0-9-]+)\s+(?:\u2014|-)\s+(.+?)\s*$", issue_title)
    if match:
        return match.group(1), match.group(2)
    return None, issue_title.strip()


def _title_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def find_ticket_file(root: Path, ticket_id: str, issue_title: str) -> Path | None:
    tickets_dir = root / "docs" / "TICKETS"
    candidates = sorted(tickets_dir.glob(f"{ticket_id}-*.md"))
    if not candidates:
        return None

    _, issue_short_title = title_from_issue_title(issue_title)
    issue_key = _title_key(issue_short_title)
    for candidate in candidates:
        body = candidate.read_text(encoding="utf-8")
        _, heading_title = parse_heading(body)
        if heading_title is not None and _title_key(heading_title) == issue_key:
            return candidate

    if len(candidates) == 1:
        return candidates[0]
    return None


def build_ticket_entries(board_items: Sequence[dict[str, Any]], root: Path) -> list[TicketEntry]:
    entries: list[TicketEntry] = []
    for index, item in enumerate(board_items):
        content = item.get("content") or {}
        issue_title = str(content.get("title") or item.get("title") or "")
        ticket_id_from_title, short_title = title_from_issue_title(issue_title)
        body = str(content.get("body") or "")
        ticket_id_from_body, heading_title = parse_heading(body)
        ticket_id = ticket_id_from_title or ticket_id_from_body
        if ticket_id is None:
            continue

        ticket_file = find_ticket_file(root, ticket_id, issue_title)
        if ticket_file is not None:
            body = ticket_file.read_text(encoding="utf-8")
            _, local_title = parse_heading(body)
            if local_title is not None:
                short_title = local_title
        elif heading_title is not None:
            short_title = heading_title

        number = content.get("number")
        if not isinstance(number, int):
            continue

        entries.append(
            TicketEntry(
                ticket_id=ticket_id,
                issue_number=number,
                issue_title=issue_title,
                title=short_title,
                status=str(item.get("status") or ""),
                priority=parse_priority(body),
                model=parse_model(body),
                dependencies=parse_dependencies(body),
                board_index=index,
                ticket_file=ticket_file,
                issue_state=content.get("state"),
            )
        )
    return entries


def github_issue_for_ticket(ticket_id: str) -> TicketEntry | None:
    compact_id = compact_ticket_id(ticket_id)
    if compact_id.isdigit():
        output = run(
            [
                "gh",
                "issue",
                "view",
                str(int(compact_id)),
                "--json",
                "number,state,title",
            ],
            capture=True,
        )
        issue = json.loads(output)
        title = str(issue.get("title") or "")
        if not title.startswith(ticket_id):
            return None
        return TicketEntry(
            ticket_id=ticket_id,
            issue_number=int(issue["number"]),
            issue_title=title,
            title=title_from_issue_title(title)[1],
            status="Done" if issue.get("state") == "CLOSED" else "",
            priority="LOW",
            model="?",
            dependencies=(),
            board_index=9999,
            issue_state=str(issue.get("state") or ""),
        )

    output = run(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "all",
            "--search",
            f"{ticket_id} in:title",
            "--json",
            "number,state,title",
            "--limit",
            "20",
        ],
        capture=True,
    )
    issues = json.loads(output)
    if not isinstance(issues, list):
        return None
    for issue in issues:
        title = str(issue.get("title") or "")
        if not title.startswith(ticket_id):
            continue
        return TicketEntry(
            ticket_id=ticket_id,
            issue_number=int(issue["number"]),
            issue_title=title,
            title=title_from_issue_title(title)[1],
            status="Done" if issue.get("state") == "CLOSED" else "",
            priority="LOW",
            model="?",
            dependencies=(),
            board_index=9999,
            issue_state=str(issue.get("state") or ""),
        )
    return None


def local_dependency_entry(root: Path, ticket_id: str) -> TicketEntry | None:
    candidates = sorted((root / "docs" / "TICKETS").glob(f"{ticket_id}-*.md"))
    if len(candidates) != 1:
        return None
    body = candidates[0].read_text(encoding="utf-8")
    _, title = parse_heading(body)
    status = (parse_field(body, "Status") or "").split()[0].strip().upper()
    if status not in {"MERGED", "DONE", "CLOSED"}:
        return None
    return TicketEntry(
        ticket_id=ticket_id,
        issue_number=0,
        issue_title=f"{ticket_id} - {title or ticket_id}",
        title=title or ticket_id,
        status="Done",
        priority=parse_priority(body),
        model=parse_model(body),
        dependencies=parse_dependencies(body),
        board_index=9999,
        ticket_file=candidates[0],
        issue_state="CLOSED",
    )


def enrich_missing_dependencies(entries: Sequence[TicketEntry], root: Path) -> list[TicketEntry]:
    result = list(entries)
    known = {entry.ticket_id for entry in result}
    missing = sorted({
        dependency
        for entry in result
        for dependency in entry.dependencies
        if dependency not in known
    })
    for dependency in missing:
        local_entry = local_dependency_entry(root, dependency)
        if local_entry is not None:
            result.append(local_entry)
            known.add(dependency)
            continue
        try:
            issue_entry = github_issue_for_ticket(dependency)
        except subprocess.CalledProcessError:
            issue_entry = None
        if issue_entry is not None and issue_entry.issue_state == "CLOSED":
            result.append(issue_entry)
            known.add(dependency)
    return result


def load_entries(root: Path) -> list[TicketEntry]:
    return enrich_missing_dependencies(build_ticket_entries(load_board_items(), root), root)


def entry_by_ticket_id(entries: Sequence[TicketEntry]) -> dict[str, TicketEntry]:
    result: dict[str, TicketEntry] = {}
    for entry in entries:
        current = result.get(entry.ticket_id)
        if current is None:
            result[entry.ticket_id] = entry
        elif current.status in DONE_STATUSES and entry.status not in DONE_STATUSES:
            result[entry.ticket_id] = entry
    return result


def dependency_satisfied(dependency_id: str, entries_by_id: dict[str, TicketEntry]) -> bool:
    dependency = entries_by_id.get(dependency_id)
    if dependency is None:
        return False
    if dependency.status in DONE_STATUSES:
        return True
    return dependency.issue_state == "CLOSED"


def blockers_for(entry: TicketEntry, entries_by_id: dict[str, TicketEntry]) -> tuple[str, ...]:
    blockers = [
        compact_ticket_id(dependency_id)
        for dependency_id in entry.dependencies
        if not dependency_satisfied(dependency_id, entries_by_id)
    ]
    return tuple(blockers)


def unblock_score(entry: TicketEntry, entries: Sequence[TicketEntry]) -> int:
    score = 0
    for downstream in entries:
        if downstream.status != "Backlog" or downstream.ticket_id == entry.ticket_id:
            continue
        if entry.ticket_id in downstream.dependencies:
            score += 1
    return score


def rank_next_tickets(entries: Sequence[TicketEntry]) -> list[TicketEntry]:
    entries_by_id = entry_by_ticket_id(entries)
    candidates = [
        entry
        for entry in entries
        if entry.status in NEXT_STATUSES and entry.issue_state != "CLOSED"
    ]

    def sort_key(entry: TicketEntry) -> tuple[int, int, int, int]:
        blockers = blockers_for(entry, entries_by_id)
        return (
            PRIORITY_ORDER.get(entry.priority, 99),
            1 if blockers else 0,
            -unblock_score(entry, entries) if not blockers else 0,
            entry.board_index,
        )

    return sorted(candidates, key=sort_key)


def load_board_items() -> list[dict[str, Any]]:
    output = run(
        [
            "gh",
            "project",
            "item-list",
            PROJECT_NUMBER,
            "--owner",
            PROJECT_OWNER,
            "--format",
            "json",
            "--limit",
            "100",
        ],
        capture=True,
    )
    data = json.loads(output)
    items = data.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def print_next_menu(entries: Sequence[TicketEntry]) -> None:
    ranked = rank_next_tickets(entries)
    entries_by_id = entry_by_ticket_id(entries)
    if not ranked:
        print(
            "Board is empty. File tickets via `bash tools/file.sh` "
            "after saving them to `docs/TICKETS/`."
        )
        return

    print(f"Up next ({len(ranked)} tickets):")
    print("")
    for index, entry in enumerate(ranked, start=1):
        blockers = blockers_for(entry, entries_by_id)
        blocked = f" ⛔ blocked by {', '.join(blockers)}" if blockers else ""
        score = unblock_score(entry, entries)
        score_text = f" unblocks {score}" if score and not blockers else ""
        print(
            f"  {index}. {entry.ticket_id} - {entry.title} "
            f"[{entry.priority}] [{entry.model}] (issue #{entry.issue_number}, {entry.status})"
            f"{blocked}{score_text}"
        )
    print("")
    print("Reply with:")
    print("  implement TICKET-XXX   start a ticket")
    print("  reorder                open the board and drag-reorder, then rerun `next`")
    print("  drop N                 close issue #N as not planned and move it to Done")
    print("  cancel                 do nothing")
    print("")
    print(
        "Blocked tickets are shown intentionally. If you explicitly start one, "
        "start_ticket warns first."
    )


def project_id() -> str:
    output = run(
        ["gh", "project", "list", "--owner", PROJECT_OWNER, "--format", "json"],
        capture=True,
    )
    projects = json.loads(output).get("projects") or []
    for project in projects:
        if str(project.get("number")) == PROJECT_NUMBER:
            return str(project["id"])
    raise RuntimeError(f"Project #{PROJECT_NUMBER} not found for {PROJECT_OWNER}.")


def project_status_ids(status_name: str) -> tuple[str, str]:
    output = run(
        [
            "gh",
            "project",
            "field-list",
            PROJECT_NUMBER,
            "--owner",
            PROJECT_OWNER,
            "--format",
            "json",
        ],
        capture=True,
    )
    fields = json.loads(output).get("fields") or []
    for field in fields:
        if field.get("name") != "Status":
            continue
        field_id = str(field["id"])
        for option in field.get("options") or []:
            if option.get("name") == status_name:
                return field_id, str(option["id"])
    raise RuntimeError(f"Status option {status_name!r} not found on project #{PROJECT_NUMBER}.")


def set_project_status(entry: TicketEntry, status_name: str) -> None:
    field_id, option_id = project_status_ids(status_name)
    item_id = board_item_id_for_issue(entry.issue_number)
    run(
        [
            "gh",
            "project",
            "item-edit",
            "--project-id",
            project_id(),
            "--id",
            item_id,
            "--field-id",
            field_id,
            "--single-select-option-id",
            option_id,
        ]
    )


def issue_state(issue_number: int) -> str:
    return run(
        ["gh", "issue", "view", str(issue_number), "--json", "state", "-q", ".state"],
        capture=True,
    ).strip()


def reconcile_done(entries: Sequence[TicketEntry]) -> None:
    moved = 0
    for entry in entries:
        if entry.status != "In review":
            continue
        state = entry.issue_state or issue_state(entry.issue_number)
        if state == "CLOSED":
            set_project_status(entry, "Done")
            print(f"Moved {entry.ticket_id} (issue #{entry.issue_number}) from In review to Done.")
            moved += 1
    if moved == 0:
        print("No closed In review items to move to Done.")


def board_item_id_for_issue(issue_number: int) -> str:
    for item in load_board_items():
        content = item.get("content") or {}
        if content.get("number") == issue_number:
            return str(item["id"])
    raise RuntimeError(f"Project item for issue #{issue_number} not found.")


def resolve_ticket(entries: Sequence[TicketEntry], ticket_arg: str) -> TicketEntry:
    ticket_id = normalize_ticket_id(ticket_arg)
    active = [
        entry
        for entry in entries
        if entry.ticket_id == ticket_id and entry.status not in DONE_STATUSES
    ]
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        details = ", ".join(f"#{entry.issue_number} ({entry.status})" for entry in active)
        raise RuntimeError(f"{ticket_id} is ambiguous among active board items: {details}")
    done = [entry for entry in entries if entry.ticket_id == ticket_id]
    if done:
        raise RuntimeError(f"{ticket_id} is already Done on the board.")
    raise RuntimeError(f"{ticket_id} was not found on the project board.")


def working_tree_status() -> str:
    return run(["git", "status", "--porcelain"], capture=True)


def ensure_clean_tree() -> None:
    status = working_tree_status().strip()
    if status:
        raise RuntimeError(f"Working tree has uncommitted changes:\n{status}")


def current_branch() -> str:
    return run(["git", "branch", "--show-current"], capture=True).strip()


def branch_matches_ticket(branch: str, ticket_id: str) -> bool:
    ticket_key = compact_ticket_id(ticket_id).lower()
    return ticket_key in branch.lower()


def slugify(value: str, *, max_words: int = 5) -> str:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return "-".join(words[:max_words]) or "ticket"


def branch_name_for(entry: TicketEntry) -> str:
    ticket_key = compact_ticket_id(entry.ticket_id).lower()
    return f"ticket-{ticket_key}-{slugify(entry.title)}"


def mark_ticket_status(ticket_file: Path | None, status: str) -> None:
    if ticket_file is None:
        return
    body = ticket_file.read_text(encoding="utf-8")
    if re.search(r"^\*\*Status:\*\*", body, flags=re.MULTILINE):
        updated = re.sub(
            r"^\*\*Status:\*\*\s*.+$",
            f"**Status:** {status}",
            body,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        updated = re.sub(
            r"^(\*\*Priority:\*\*\s*.+)$",
            rf"\1\n**Status:** {status}",
            body,
            count=1,
            flags=re.MULTILINE,
        )
    if updated != body:
        ticket_file.write_text(updated, encoding="utf-8")


def start_ticket(ticket_arg: str, root: Path) -> None:
    entries = load_entries(root)
    reconcile_done(entries)
    entries = load_entries(root)
    entry = resolve_ticket(entries, ticket_arg)
    blockers = blockers_for(entry, entry_by_ticket_id(entries))
    if blockers:
        print(
            f"Warning: {entry.ticket_id} is blocked by {', '.join(blockers)}. "
            "Continuing by explicit request."
        )

    branch = current_branch()
    if branch == "main":
        ensure_clean_tree()
        run(["git", "pull", "--ff-only", "origin", "main"])
        branch_name = branch_name_for(entry)
        run(["git", "checkout", "-b", branch_name])
    else:
        if not branch_matches_ticket(branch, entry.ticket_id):
            raise RuntimeError(
                f"Current branch {branch!r} does not look like it belongs to {entry.ticket_id}."
            )
        branch_name = branch
        print(f"Reusing current branch {branch_name}.")

    mark_ticket_status(entry.ticket_file, "IN_PROGRESS")
    set_project_status(entry, "In progress")
    print(f"Branch: {branch_name}")


def finish_ticket(ticket_arg: str, root: Path) -> None:
    entries = load_entries(root)
    entry = resolve_ticket(entries, ticket_arg)
    branch = current_branch()
    if branch == "main":
        raise RuntimeError("Refusing to finish from main.")
    if not branch_matches_ticket(branch, entry.ticket_id):
        raise RuntimeError(
            f"Current branch {branch!r} does not look like it belongs to {entry.ticket_id}."
        )
    ensure_clean_tree()

    run(["git", "push", "-u", "origin", branch])
    set_project_status(entry, "In review")
    body = f"Implements {entry.ticket_id}.\n\nCloses #{entry.issue_number}"
    pr_url = run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--title",
            f"{entry.ticket_id} - {entry.title}",
            "--body",
            body,
        ],
        capture=True,
    ).strip()
    print(pr_url)


def print_dependency_report(entries: Sequence[TicketEntry]) -> None:
    entries_by_id = entry_by_ticket_id(entries)
    for entry in rank_next_tickets(entries):
        blockers = blockers_for(entry, entries_by_id)
        if blockers:
            print(f"{entry.ticket_id}: blocked by {', '.join(blockers)}")
        else:
            score = unblock_score(entry, entries)
            suffix = f" (unblocks {score})" if score else ""
            print(f"{entry.ticket_id}: eligible{suffix}")


def doctor(root: Path) -> int:
    exit_code = 0
    print(f"Repo: {root}")
    branch = current_branch()
    print(f"Branch: {branch or '<detached>'}")

    status = working_tree_status().strip()
    if status:
        print("Dirty tree: yes")
        print(status)
        exit_code = 1
    else:
        print("Dirty tree: no")

    stale_paths = [
        root / "docs" / "CONTEXT.md",
        root / "tools" / "regen_context.py",
        root / ".github" / "workflows" / "update-context.yml",
        root / ".github" / "workflows" / "post-merge-housekeeping.yml",
    ]
    stale_existing = [path.relative_to(root) for path in stale_paths if path.exists()]
    if stale_existing:
        print("Stale retired files present:")
        for path in stale_existing:
            print(f"  {path}")
        exit_code = 1
    else:
        print("Stale retired files: none")

    entries = load_entries(root)
    active_ids: dict[str, list[TicketEntry]] = {}
    for entry in entries:
        if entry.status in ACTIVE_STATUSES:
            active_ids.setdefault(entry.ticket_id, []).append(entry)
    duplicates = {ticket_id: rows for ticket_id, rows in active_ids.items() if len(rows) > 1}
    if duplicates:
        print("Duplicate active ticket IDs:")
        for ticket_id, rows in duplicates.items():
            issues = ", ".join(f"#{row.issue_number} ({row.status})" for row in rows)
            print(f"  {ticket_id}: {issues}")
        exit_code = 1
    else:
        print("Board duplicate active IDs: none")

    print("Dependency report:")
    print_dependency_report(entries)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("next")
    subparsers.add_parser("doctor")

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("ticket")

    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("ticket")

    args = parser.parse_args(argv)
    root = repo_root()

    try:
        if args.command == "next":
            print_next_menu(load_entries(root))
        elif args.command == "doctor":
            return doctor(root)
        elif args.command == "start":
            start_ticket(args.ticket, root)
        elif args.command == "finish":
            finish_ticket(args.ticket, root)
        else:  # pragma: no cover - argparse prevents this
            raise RuntimeError(f"Unknown command {args.command!r}.")
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"Error: {details}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
