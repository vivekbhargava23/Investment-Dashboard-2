# TICKET-003 — JSON Transaction Repository (port + adapter)

**Status:** READY
**Priority:** P0
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** _pending_
**Depends on:** TICKET-001 (domain models must exist)

## Problem

We have domain types (Transaction, Money, Currency) from TICKET-001 and the FIFO engine from TICKET-002. Both are pure functions — they don't know how to load or save anything. We need:

1. A **port** (`Protocol`) at `app/ports/repository.py` that defines the abstract `TransactionRepository` interface.
2. A **JSON adapter** at `app/adapters/repo_json/` that implements that port by reading/writing a JSON file on disk.

After this ticket, the rest of the app can save transactions and replay them — i.e. the system becomes stateful and persistent, but only via the abstraction. The repository can later be swapped for SQLite without touching any caller.

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-03:

1. **Flat list of transactions** in the JSON file, not grouped by ticker. Tickers are derived; transactions are atomic.
2. **Atomic writes** — write to `<path>.tmp`, fsync, then `os.replace` to the final path. Prevents corruption from interrupted writes.
3. **Schema versioning** — top-level `"version": 1` field. Future migrations can detect and upgrade old files.
4. **Pydantic-native serialization** — use `model_dump_json()` and `model_validate_json()`. `Decimal` serializes as string, preserving precision.
5. **The port lives in `app/ports/`, the adapter in `app/adapters/repo_json/`.** Domain and services depend on the port only; nothing imports from the adapter except the wiring in `app/ui/app.py` (eventually).

## Acceptance criteria

### `app/ports/repository.py` — the abstract interface

- [ ] `TransactionRepository` is a `typing.Protocol` (not an ABC). Methods:
  - `load_all(self) -> list[Transaction]` — returns all transactions, in stored order
  - `save_all(self, transactions: Sequence[Transaction]) -> None` — replaces the entire stored list atomically
  - `add(self, transaction: Transaction) -> None` — appends one transaction
  - `update(self, transaction: Transaction) -> None` — replaces an existing transaction by `id`; raises `TransactionNotFoundError` if not present
  - `delete(self, transaction_id: str) -> None` — removes by id; raises `TransactionNotFoundError` if not present
  - `get(self, transaction_id: str) -> Transaction` — fetches one by id; raises `TransactionNotFoundError` if not present
- [ ] `TransactionNotFoundError(Exception)` defined in this file (the port file, because the error is part of the contract).
- [ ] `RepositoryCorruptedError(Exception)` defined here too — raised when the underlying storage is unreadable or malformed.

### `app/adapters/repo_json/__init__.py`

- [ ] Package init re-exports `JsonTransactionRepository` so callers can `from app.adapters.repo_json import JsonTransactionRepository`.

### `app/adapters/repo_json/json_repo.py` — the concrete adapter

- [ ] `JsonTransactionRepository` class. Constructor: `__init__(self, path: Path)`. Stores the path; does NOT eagerly read the file (allow constructing the repo without the file existing yet).
- [ ] **File format on disk:**
  ```json
  {
    "version": 1,
    "transactions": [
      {
        "id": "uuid-string",
        "type": "buy",
        "ticker": "NVDA",
        "trade_date": "2024-03-15",
        "shares": "10.0000",
        "price_native": {"amount": "887.4200", "currency": "USD"},
        "fees_native": null,
        "fx_rate_eur": "0.9200",
        "notes": null
      }
    ]
  }
  ```
  Note `Decimal` values serialize as strings (Pydantic v2 default); preserve this.

- [ ] **`load_all` behaviour:**
  - If the file does not exist → return `[]` (empty list, no error). This is the "fresh install" case.
  - If the file exists but is empty (0 bytes) → raise `RepositoryCorruptedError`.
  - If the file is unreadable JSON → raise `RepositoryCorruptedError` with the underlying error chained.
  - If `version` is missing or not `1` → raise `RepositoryCorruptedError("Unsupported schema version: ...")`.
  - Otherwise: parse all transactions via `Transaction.model_validate(...)` and return them in stored order.

- [ ] **`save_all` behaviour (atomic write):**
  - Build the JSON dict: `{"version": 1, "transactions": [tx.model_dump(mode="json") for tx in transactions]}`.
  - Serialize with `json.dumps(data, indent=2, sort_keys=False)` for human readability.
  - Write to a sibling temp file: `<path>.tmp` (e.g. `data/portfolio.json.tmp`).
  - `flush()` and `os.fsync(fd)` the temp file before closing.
  - `os.replace(tmp_path, final_path)` for atomic rename.
  - On any exception, clean up the `.tmp` file before re-raising.
  - Ensure the parent directory exists (`path.parent.mkdir(parents=True, exist_ok=True)`).

- [ ] **`add` behaviour:**
  - Internally: `txs = self.load_all(); txs.append(transaction); self.save_all(txs)`.
  - If a transaction with the same `id` already exists → raise `ValueError("Transaction with id ... already exists")`.

- [ ] **`update` behaviour:**
  - Internally: `load_all()`, find the transaction by id, replace in-place (preserve list order), `save_all()`.
  - If not found → raise `TransactionNotFoundError(transaction.id)`.

- [ ] **`delete` behaviour:**
  - `load_all()`, filter out the matching id, `save_all()`.
  - If id not found → raise `TransactionNotFoundError(transaction_id)`.

- [ ] **`get` behaviour:**
  - `load_all()`, scan for matching id, return.
  - If not found → raise `TransactionNotFoundError(transaction_id)`.

### Tests

All in `tests/integration/test_json_repo.py` (this is integration-flavoured because it touches the filesystem; we still run it under pytest with `tmp_path` fixture).

#### Basic round-trip
- [ ] **Empty repo, empty file**: construct repo with non-existent path → `load_all() == []`.
- [ ] **Save-then-load round-trip**: build 3 transactions, `save_all`, construct a fresh repo on the same path, `load_all` returns equivalent list (ids preserved, all fields equal).
- [ ] **`add` appends**: empty repo, `add(tx1)`, `add(tx2)`, `load_all()` returns `[tx1, tx2]`.
- [ ] **`get` finds existing**: returns the same Transaction.
- [ ] **`get` raises on missing**: `TransactionNotFoundError` with the unknown id in the message.
- [ ] **`update` replaces by id**: build a tx, modify it (new shares value via `model_copy`), call `update()`, `get(id)` returns the modified version.
- [ ] **`update` raises on missing**: `TransactionNotFoundError`.
- [ ] **`delete` removes**: 3 txs, delete middle one, `load_all` returns 2 in order.
- [ ] **`delete` raises on missing**: `TransactionNotFoundError`.
- [ ] **`add` raises on duplicate id**: same id twice → `ValueError`.

#### Atomic write
- [ ] **`.tmp` does not persist after success**: after `save_all` succeeds, only `portfolio.json` exists — no `.tmp` left over.
- [ ] **Crash during write does not corrupt main file**: simulate by patching `os.replace` to raise; original file should still be intact.
  - Setup: write valid file with one tx. Patch `os.replace` to raise IOError. Call `save_all` with new data. Assert the IOError propagates AND the original file still has the original content (not the new content, not corrupted).

#### Corruption handling
- [ ] **Empty file raises**: write empty file at the path, `load_all` raises `RepositoryCorruptedError`.
- [ ] **Malformed JSON raises**: write `"this is not json"` to the path, `load_all` raises `RepositoryCorruptedError`.
- [ ] **Missing version raises**: write `{"transactions": []}` (no version), `load_all` raises `RepositoryCorruptedError`.
- [ ] **Wrong version raises**: write `{"version": 2, "transactions": []}`, `load_all` raises `RepositoryCorruptedError`.
- [ ] **Invalid transaction shape raises**: write `{"version": 1, "transactions": [{"id": "not-uuid"}]}` (missing required fields), `load_all` raises `RepositoryCorruptedError` (Pydantic ValidationError chained).

#### Decimal precision
- [ ] **Round-trip preserves precision**: a transaction with `shares=Decimal("0.0001")`, `price=Decimal("12345.6789")`, `fx_rate=Decimal("0.9234")` — save, load, all values exactly equal (no float drift).

#### Parent dir creation
- [ ] **Creates parent directory**: pass a path like `tmp_path / "deep" / "nested" / "portfolio.json"`, call `save_all`, file exists at that path.

### Lints / quality
- [ ] `pytest` — all tests pass (existing + new)
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes; **strict on `app/domain/`**, `app/ports/` should also be clean
- [ ] `lint-imports` — passes; in particular:
  - `app.ports` does not import from `app.adapters`
  - `app.adapters.repo_json` may import from `app.ports` and `app.domain`, but not from `app.services` or `app.ui`

### State updates (per CLAUDE.md session-end ritual)
- [ ] `docs/SESSION_LOG.md` appended
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-003 → IN_REVIEW)
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-003 → IN_REVIEW)
- [ ] Ticket file `Status: IN_REVIEW`
- [ ] PR opened via `gh pr create --fill --base main`

## Files created

```
app/ports/repository.py
app/adapters/repo_json/__init__.py
app/adapters/repo_json/json_repo.py
tests/integration/__init__.py     ← may already exist; create if missing
tests/integration/test_json_repo.py
```

## Files possibly updated

```
app/ports/__init__.py             ← export TransactionRepository, errors
app/adapters/__init__.py          ← (no change needed, but ensure file exists)
docs/TICKETS/BACKLOG.md
```

## Out of scope

- SQLite or any other backing store — just a port behind which we could swap later
- FX adapter — folded into TICKET-005
- Price adapters — TICKET-005
- Concurrent / multi-process access (we are single-user, single-process)
- Migration from version 1 → 2 schemas (no real version 2 yet)
- Encryption at rest (the file lives on the user's machine; not our problem yet)

## Notes

### On `Path` vs `str`

Always `Path` in the port and adapter signature. If `Settings.portfolio_json_path` is a string, the wiring code converts: `JsonTransactionRepository(Path(settings.portfolio_json_path))`.

### On the temp file location

Put the temp file *next to* the final file (`portfolio.json.tmp` next to `portfolio.json`), not in the system temp dir. Reason: `os.replace` requires source and destination on the same filesystem to be atomic. Using `/tmp/` may cross filesystems.

### On `os.fsync`

Yes, we want it. Without `fsync`, the OS may buffer the write in memory; if the laptop loses power between `write` and `replace`, the temp file may be empty. `fsync` forces the bytes to actual storage. The cost is a few milliseconds — irrelevant.

```python
with open(tmp_path, "w") as f:
    f.write(content)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp_path, final_path)
```

### On exception cleanup

If anything goes wrong between writing the temp file and the rename, leave the system in a clean state — delete the temp file. Pattern:

```python
try:
    # write tmp
    # fsync
    # replace
except Exception:
    if tmp_path.exists():
        tmp_path.unlink(missing_ok=True)
    raise
```

### On Pydantic serialization

`Transaction.model_dump(mode="json")` returns a plain Python dict where `Decimal` is converted to string and `date` to ISO format. `Transaction.model_validate(dict)` reverses it cleanly. Don't roll a custom encoder.

### On the `version` field's purpose

It's not just a placeholder. The day we add a `SPLIT` transaction type or rename `fees_native` to `commission_native`, we bump `version` to 2 and add a migration step. The check today (`raise on != 1`) means we'll *fail loud* on old files instead of silently misinterpreting them. That's the value.

### What this ticket DOES NOT do

It does not enforce the architectural rule "domain doesn't import adapters" — `import-linter` does, and the rule already exists in `.importlinter`. This ticket is just careful not to violate it.

It also does not wire the repository into any UI or service. That's the next ticket(s). After this ticket lands, the repository exists but nothing in the running app uses it yet.
