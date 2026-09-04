"""
Architectural invariants — the guarantees that make Warden Warden.

If any of these break, the pitch is compromised. Failing this file is a hard
stop, regardless of what other tests do.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"


def _module_files(pkg: str) -> list[Path]:
    return sorted((APP_ROOT / pkg).rglob("*.py"))


def _find_imports(path: Path) -> set[str]:
    """Return the set of top-level module names imported from a file."""
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


# ---- Invariant 1 -----------------------------------------------------------


def test_warden_package_never_imports_llm_or_razorpay_sdk_directly():
    """
    Warden Core is the authority. It must be pure Python + DB + audit +
    (indirectly, via app.payments) the payment adapter. It must not reach
    into the agent package, nor import an LLM SDK, nor import the razorpay
    SDK directly — that lives in app.payments.
    """
    forbidden_prefixes = ("app.agents", "anthropic", "openai", "razorpay")
    offenders: list[tuple[str, str]] = []
    for path in _module_files("warden"):
        for imp in _find_imports(path):
            if any(imp == p or imp.startswith(p + ".") for p in forbidden_prefixes):
                offenders.append((str(path.relative_to(APP_ROOT.parent)), imp))
    assert not offenders, (
        "Warden package imported forbidden modules: " + repr(offenders)
    )


# ---- Invariant 2 -----------------------------------------------------------


def test_agents_package_never_imports_razorpay():
    """The agent may propose. It may not touch the payment provider."""
    for path in _module_files("agents"):
        for imp in _find_imports(path):
            assert not imp.startswith(
                "razorpay"
            ), f"{path.relative_to(APP_ROOT.parent)} imports razorpay"


# ---- Invariant 3 -----------------------------------------------------------


def test_only_the_coordinator_persists_decisions():
    """
    Only app.warden.coordinator may INSERT into decisions or mutate mandate
    counters. Screen for `session.add(Decision(` and
    `apply_successful_action(` outside that file.
    """
    banned_substrings = ["session.add(Decision(", "apply_successful_action("]
    allowed_files = {
        APP_ROOT / "warden" / "coordinator.py",
        APP_ROOT / "services" / "mandate_state.py",  # defines the helper itself
    }
    offenders: list[tuple[str, str]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path in allowed_files:
            continue
        text = path.read_text()
        for needle in banned_substrings:
            if needle in text:
                offenders.append((str(path.relative_to(APP_ROOT.parent)), needle))
    assert not offenders, (
        "Files outside app/warden/coordinator.py mutate decisions/mandate: "
        + repr(offenders)
    )


# ---- Invariant 4 -----------------------------------------------------------


def test_only_warden_may_import_payments():
    """
    The payment layer (app.payments) is the ONLY place that talks to Razorpay.
    Only app.warden.* may import it. In particular the API layer, the agent,
    services, and audit must NOT import app.payments.

    This preserves the Stage 5 rule: 'the Warden remains the only component
    allowed to invoke financial tools'.
    """
    allowed_dirs = {APP_ROOT / "warden", APP_ROOT / "payments"}
    offenders: list[tuple[str, str]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        # Skip files that are inside allowed dirs.
        if any(str(path).startswith(str(d) + "/") or path == d for d in allowed_dirs):
            continue
        for imp in _find_imports(path):
            if imp == "app.payments" or imp.startswith("app.payments."):
                offenders.append((str(path.relative_to(APP_ROOT.parent)), imp))
    assert not offenders, (
        "Only app.warden.* may import app.payments; found: " + repr(offenders)
    )
