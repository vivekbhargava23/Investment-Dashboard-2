#!/usr/bin/env python3
"""Auto-generate docs/CONTEXT.md from the current repo state.

Run: python tools/regen_context.py
Writes: docs/CONTEXT.md

Sections emitted (in order):
  Up next · In progress · In review · Recently done ·
  ADRs · File tree · Public interfaces · UI surface ·
  Data file shape · Open issues · Open PRs · Recent merges · Recent sessions

Up next, In progress, In review, Recently done are sourced from the GitHub
Projects board (project #2). All other sections come from the local repo and
the GitHub Issues/PRs API.
"""
from __future__ import annotations

import ast
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "CONTEXT.md"
DECISIONS_DIR = REPO_ROOT / "docs" / "DECISIONS"
APP_DIR = REPO_ROOT / "app"
TESTS_DIR = REPO_ROOT / "tests"
PAGES_DIR = REPO_ROOT / "app" / "ui" / "pages"
DATA_JSON = REPO_ROOT / "data" / "portfolio.json"

PROJECT_NUMBER = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_gh(*args: str) -> str:
    """Run a gh CLI command; return stdout on success or an error message."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"<gh CLI error: {result.stderr.strip()}>"
        return result.stdout.strip()
    except FileNotFoundError:
        return "<gh CLI unavailable at generation time — section skipped>"
    except subprocess.TimeoutExpired:
        return "<gh CLI timed out at generation time — section skipped>"


def _file_tree(roots: list[Path], ignore_patterns: set[str]) -> str:
    """Produce a tree listing for the given root directories."""
    lines: list[str] = []

    def _walk(path: Path, prefix: str) -> None:
        try:
            children = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        visible = [
            c for c in children
            if c.name not in ignore_patterns and not c.name.startswith("__pycache__")
        ]
        for i, child in enumerate(visible):
            connector = "└── " if i == len(visible) - 1 else "├── "
            lines.append(f"{prefix}{connector}{child.name}")
            if child.is_dir():
                extension = "    " if i == len(visible) - 1 else "│   "
                _walk(child, prefix + extension)

    for root in roots:
        if root.exists():
            lines.append(str(root.relative_to(REPO_ROOT)) + "/")
            _walk(root, "")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Board sections
# ---------------------------------------------------------------------------

def _board_items_by_status() -> dict[str, list[dict]] | str:
    """Return board items grouped by status column name, or an error string."""
    raw = _run_gh(
        "project", "item-list", str(PROJECT_NUMBER),
        "--owner", "@me",
        "--format", "json",
        "--limit", "100",
    )
    if raw.startswith("<"):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "<could not parse gh project output>"

    grouped: dict[str, list[dict]] = {}
    for item in data.get("items", []):
        status = item.get("status", "")
        grouped.setdefault(status, []).append(item)
    return grouped


def _format_board_item(item: dict) -> str:
    content = item.get("content", {})
    number = content.get("number", "?")
    title = content.get("title", "(no title)")
    # Extract priority label from issue title if possible, or leave blank
    priority = ""
    for part in title.split("["):
        if len(part) > 0 and part.rstrip("]").upper() in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            priority = f" [{part.rstrip(']').upper()}]"
            break
    # Try to extract ticket ID from title
    return f"- {title} (issue #{number}){priority}"


def section_board() -> str:
    """Emit Up next, In progress, In review, Recently done from the project board."""
    result = _board_items_by_status()
    if isinstance(result, str):
        lines = [
            "## Up next\n\n<project board unavailable at generation time — section skipped>",
            "## In progress\n\n<project board unavailable at generation time — section skipped>",
            "## In review\n\n<project board unavailable at generation time — section skipped>",
            "## Recently done\n\n<project board unavailable at generation time — section skipped>",
        ]
        return "\n\n---\n\n".join(lines) + "\n"

    grouped = result

    def _section(header: str, status_key: str, limit: int | None = None) -> str:
        items = grouped.get(status_key, [])
        if limit is not None:
            items = sorted(items, key=lambda x: x.get("updatedAt", ""), reverse=True)[:limit]
        if not items:
            return f"## {header}\n\n(none)"
        body = "\n".join(_format_board_item(i) for i in items)
        return f"## {header}\n\n{body}"

    # Up next: Ready first, then Backlog
    ready_items = grouped.get("Ready", [])
    backlog_items = grouped.get("Backlog", [])

    up_next_lines = []
    if ready_items:
        up_next_lines.append("Ready (vetted):")
        up_next_lines.extend(f"  {_format_board_item(i)}" for i in ready_items)
    if backlog_items:
        up_next_lines.append("Backlog:")
        up_next_lines.extend(f"  {_format_board_item(i)}" for i in backlog_items)

    if up_next_lines:
        up_next_section = "## Up next\n\n" + "\n".join(up_next_lines)
    else:
        up_next_section = "## Up next\n\n(none)"

    in_progress_section = _section("In progress", "In progress")
    in_review_section = _section("In review", "In review")
    recently_done_section = _section("Recently done", "Done", limit=10)

    return "\n\n---\n\n".join([
        up_next_section,
        in_progress_section,
        in_review_section,
        recently_done_section,
    ]) + "\n"


# ---------------------------------------------------------------------------
# Existing section generators (unchanged)
# ---------------------------------------------------------------------------

def section_adrs() -> str:
    if not DECISIONS_DIR.exists():
        return "## ADRs (titles only)\n\n<docs/DECISIONS/ not found>\n"
    lines: list[str] = []
    for md in sorted(DECISIONS_DIR.glob("*.md")):
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("# ADR-"):
                lines.append(f"- {line[2:].strip()}")
                break
    if not lines:
        return "## ADRs (titles only)\n\n<no ADR files found>\n"
    return "## ADRs (titles only)\n\n" + "\n".join(lines) + "\n"


def section_file_tree() -> str:
    # CONTEXT.md excluded: it's auto-generated and would break idempotency on second run
    ignore = {
        "__pycache__", ".git", ".mypy_cache", ".ruff_cache",
        "*.pyc", ".pytest_cache", "CONTEXT.md",
    }
    roots = [APP_DIR, REPO_ROOT / "docs"]
    tree = _file_tree(roots, ignore)
    return f"## File tree\n\n```\n{tree}\n```\n"


def _format_annotation(node: ast.expr | None) -> str:
    if node is None:
        return ""
    return ast.unparse(node)


def _extract_arg(arg: ast.arg) -> str:
    annotation = _format_annotation(arg.annotation)
    return f"{arg.arg}: {annotation}" if annotation else arg.arg


def _extract_func_sig(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    all_args: list[str] = []
    # positional only (Python 3.8+)
    for a in args.posonlyargs:
        all_args.append(_extract_arg(a))
    if args.posonlyargs:
        all_args.append("/")
    for a in args.args:
        all_args.append(_extract_arg(a))
    if args.vararg:
        all_args.append(f"*{_extract_arg(args.vararg)}")
    elif args.kwonlyargs:
        all_args.append("*")
    for a in args.kwonlyargs:
        all_args.append(_extract_arg(a))
    if args.kwarg:
        all_args.append(f"**{_extract_arg(args.kwarg)}")

    ret = _format_annotation(node.returns)
    ret_str = f" -> {ret}" if ret else ""
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(all_args)}){ret_str}"


def _extract_class_info(node: ast.ClassDef) -> list[str]:
    """Return class header + field annotations (for Protocol/Pydantic/dataclass)."""
    bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
    header = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
    fields: list[str] = []
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            ann = _format_annotation(item.annotation)
            fields.append(f"    {item.target.id}: {ann}")
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Include methods inside Protocol classes (all methods) or
            # include only public methods for regular classes
            is_private = item.name.startswith("_") and item.name != "__init__"
            # For Protocol classes (base has 'Protocol'), include all methods
            base_names = {ast.unparse(b) for b in node.bases}
            is_protocol = any("Protocol" in b for b in base_names)
            if not is_private or is_protocol:
                sig = _extract_func_sig(item)
                fields.append(f"    {sig}")
    return [header] + fields


def section_public_interfaces() -> str:
    if not APP_DIR.exists():
        return "## Public interfaces (extracted from app/)\n\n<app/ not found>\n"
    parts: list[str] = []
    for py_file in sorted(APP_DIR.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue
        rel = py_file.relative_to(REPO_ROOT)
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(rel))
        except SyntaxError:
            parts.append(f"### {rel}\n\n<syntax error — could not parse>\n")
            continue

        file_parts: list[str] = []
        for node in ast.walk(tree):
            # Only top-level nodes
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            # Must be a direct child of the module
            if not any(
                isinstance(p, ast.Module) and node in p.body
                for p in [tree]
            ):
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                file_parts.append(_extract_func_sig(node))
            elif isinstance(node, ast.ClassDef):
                file_parts.extend(_extract_class_info(node))

        if file_parts:
            parts.append(f"### {rel}\n\n```python\n" + "\n".join(file_parts) + "\n```\n")

    if not parts:
        return "## Public interfaces (extracted from app/)\n\n<no public interfaces found>\n"
    return "## Public interfaces (extracted from app/)\n\n" + "\n".join(parts)


def section_ui_surface() -> str:
    if not PAGES_DIR.exists():
        return "## UI surface (Streamlit pages)\n\n<app/ui/pages/ not found>\n"
    lines: list[str] = []
    for py_file in sorted(PAGES_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        rel = py_file.relative_to(REPO_ROOT)
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            docstring = ast.get_docstring(tree)
            if docstring:
                first_line = docstring.splitlines()[0].strip()
            else:
                # Fallback: first non-import, non-comment, non-blank line
                first_line = "<no docstring>"
                for src_line in source.splitlines():
                    stripped = src_line.strip()
                    if stripped and not stripped.startswith(("#", "import", "from", '"""', "'''")):
                        first_line = stripped[:120]
                        break
        except SyntaxError:
            first_line = "<syntax error>"
        lines.append(f"- `{rel}` — {first_line}")
    if not lines:
        return "## UI surface (Streamlit pages)\n\n<no page files found>\n"
    return "## UI surface (Streamlit pages)\n\n" + "\n".join(lines) + "\n"


def _describe_value(val: object) -> str:
    if isinstance(val, dict):
        return f"dict[{len(val)} keys]"
    if isinstance(val, list):
        return f"list[{len(val)} items]"
    if isinstance(val, str):
        sample = val[:40].replace("\n", "\\n")
        return f"str ({sample!r})"
    if isinstance(val, (int, float, bool)):
        return f"{type(val).__name__} ({val!r})"
    if val is None:
        return "null"
    return type(val).__name__


def section_data_shape() -> str:
    header = "## Data file shape (data/portfolio.json)\n\n"
    if not DATA_JSON.exists():
        return header + "<portfolio.json not found or unparseable at generation time>\n"
    try:
        data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return header + "<portfolio.json not found or unparseable at generation time>\n"

    if not isinstance(data, dict):
        return header + f"<top-level is {type(data).__name__}, not dict>\n"

    lines: list[str] = []
    for key, val in data.items():
        lines.append(f"- `{key}`: {_describe_value(val)}")
        if isinstance(val, dict):
            for subkey, subval in list(val.items())[:5]:
                lines.append(f"    - `{subkey}`: {_describe_value(subval)}")
            if len(val) > 5:
                lines.append(f"    - ... ({len(val) - 5} more keys)")
        elif isinstance(val, list) and val:
            item = val[0]
            if isinstance(item, dict):
                for subkey, subval in list(item.items())[:5]:
                    lines.append(f"    - item[0][`{subkey}`]: {_describe_value(subval)}")
                if len(item) > 5:
                    lines.append(f"    - ... ({len(item) - 5} more keys in item[0])")
    return header + "\n".join(lines) + "\n"


def section_open_issues() -> str:
    raw = _run_gh(
        "issue", "list",
        "--state", "open",
        "--json", "number,title,labels",
        "--limit", "50",
    )
    if raw.startswith("<"):
        return f"## Open issues\n\n{raw}\n"
    try:
        issues = json.loads(raw)
    except json.JSONDecodeError:
        return "## Open issues\n\n<could not parse gh output>\n"
    if not issues:
        return "## Open issues\n\n(none)\n"
    lines = []
    for issue in issues:
        labels = ", ".join(lbl["name"] for lbl in issue.get("labels", []))
        label_str = f" [{labels}]" if labels else ""
        lines.append(f"- #{issue['number']} — {issue['title']}{label_str}")
    return "## Open issues\n\n" + "\n".join(lines) + "\n"


def section_open_prs() -> str:
    raw = _run_gh(
        "pr", "list",
        "--state", "open",
        "--json", "number,title",
        "--limit", "20",
    )
    if raw.startswith("<"):
        return f"## Open PRs\n\n{raw}\n"
    try:
        prs = json.loads(raw)
    except json.JSONDecodeError:
        return "## Open PRs\n\n<could not parse gh output>\n"
    if not prs:
        return "## Open PRs\n\n(none)\n"
    lines = [f"- #{pr['number']} — {pr['title']}" for pr in prs]
    return "## Open PRs\n\n" + "\n".join(lines) + "\n"


def section_recent_merges() -> str:
    raw = _run_gh(
        "pr", "list",
        "--state", "merged",
        "--limit", "10",
        "--json", "number,title,mergedAt",
    )
    if raw.startswith("<"):
        return f"## Recent merges (last 10)\n\n{raw}\n"
    try:
        prs = json.loads(raw)
    except json.JSONDecodeError:
        return "## Recent merges (last 10)\n\n<could not parse gh output>\n"
    if not prs:
        return "## Recent merges (last 10)\n\n(none)\n"
    lines = []
    for pr in prs:
        merged_at = pr.get("mergedAt", "")[:10]
        lines.append(f"- #{pr['number']} — {pr['title']} (merged {merged_at})")
    return "## Recent merges (last 10)\n\n" + "\n".join(lines) + "\n"


def section_recent_sessions() -> str:
    import re
    log_path = REPO_ROOT / "docs" / "SESSION_LOG.md"
    if not log_path.exists():
        return "## Recent sessions\n\n<no entries>\n"
    text = log_path.read_text(encoding="utf-8")
    heading_re = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) — (TICKET-\S+)", re.MULTILINE)
    pr_re = re.compile(r"\*\*PR:\*\* https?://\S+/pull/(\d+)")
    entries: list[str] = []
    for m in heading_re.finditer(text):
        date_time = m.group(1)
        ticket = m.group(2)
        # Search for a PR line within the next 300 chars of this heading
        window = text[m.start(): m.start() + 300]
        pr_match = pr_re.search(window)
        pr_part = f" (PR #{pr_match.group(1)})" if pr_match else ""
        entries.append(f"- {date_time} — {ticket}{pr_part}")
    if not entries:
        return "## Recent sessions\n\n<no entries>\n"
    return "## Recent sessions\n\n" + "\n".join(entries[:10]) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate() -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = (
        f"# CONTEXT — auto-generated {ts}\n\n"
        "This file is auto-generated by `tools/regen_context.py` on every merge to main "
        "(via `.github/workflows/update-context.yml`). **Do not hand-edit.** "
        "Edits will be overwritten on the next merge.\n\n"
        "It gives the chat surface a complete snapshot of the repo: project state, "
        "ADRs, file layout, public Python interfaces, Streamlit page inventory, "
        "data shape, and GitHub activity. No manual paste required.\n\n"
        "Up next, In progress, In review, Recently done are sourced from the GitHub "
        f"Projects board (project #{PROJECT_NUMBER}).\n\n"
        "---\n\n"
    )
    sections = [
        section_board(),
        section_adrs(),
        section_file_tree(),
        section_public_interfaces(),
        section_ui_surface(),
        section_data_shape(),
        section_open_issues(),
        section_open_prs(),
        section_recent_merges(),
        section_recent_sessions(),
    ]
    return header + "\n---\n\n".join(s.rstrip() + "\n" for s in sections)


def main() -> None:
    content = generate()
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    lines = content.count("\n")
    print(f"Written {OUTPUT_PATH} ({lines} lines)")


if __name__ == "__main__":
    main()
