"""Smoke tests for tools/regen_context.py — verifies AST extraction doesn't regress."""
from __future__ import annotations

# We import the module functions directly so any import-time errors surface clearly.
from tools.regen_context import (
    section_adrs,
    section_public_interfaces,
    section_tests_inventory,
    section_ui_surface,
)


def test_public_interfaces_contains_core_models() -> None:
    """AST extraction must find the core domain models from app/domain/models.py."""
    output = section_public_interfaces()
    for symbol in ("class Money", "class Transaction", "class Position", "class OpenLot"):
        assert symbol in output, f"Expected '{symbol}' in Public interfaces section"


def test_public_interfaces_contains_compute_positions() -> None:
    output = section_public_interfaces()
    assert "def compute_positions" in output


def test_public_interfaces_contains_port_protocols() -> None:
    output = section_public_interfaces()
    assert "class TransactionRepository" in output
    assert "class PriceProvider" in output
    assert "class FxProvider" in output


def test_public_interfaces_non_empty() -> None:
    output = section_public_interfaces()
    assert len(output) > 500, "Public interfaces section suspiciously short"


def test_adrs_non_empty() -> None:
    output = section_adrs()
    assert "ADR-" in output, "Expected at least one ADR entry"


def test_ui_surface_non_empty() -> None:
    output = section_ui_surface()
    # At least one page should be listed
    assert "app/ui/pages/" in output


def test_tests_inventory_non_empty() -> None:
    output = section_tests_inventory()
    # The section lists test function names without the `def` prefix
    assert "test_" in output and "## Tests inventory" in output
