"""Static-analysis lifecycle tests for src/ui/main_window.py.

These tests act as a lint gate: they parse the module source with the ``ast``
module and assert structural invariants without importing the module (which
would require a running QApplication and all heavy ML dependencies).

test_no_qtimer_in_worker_thread
    Ensures that daemon-thread target functions spawned from the main window
    never reference QTimer, QObject, QThread, or any other main-thread-only
    Qt type.  Creating Qt objects off the main thread causes silent crashes
    and race conditions that are extremely hard to diagnose at runtime.

    The check walks every function named ``_run`` (the conventional name used
    for the inner daemon-thread body in this codebase) and asserts no
    ``ast.Name`` node resolves to a known main-thread-only Qt class.

test_spawn_feature_collection_single_call
    Ensures ``_spawn_feature_collection`` is called exactly once inside
    ``_on_review_generate``, guarding against the D2 duplicate-call
    regression described in the task context.

test_spawn_feature_collection_def_before_call
    Ensures the nested helper function ``_spawn_feature_collection`` is
    *defined* (``ast.FunctionDef``) before it is *called* (``ast.Call``)
    within the body of ``_on_review_generate``, so there is no
    call-before-def NameError at runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAIN_WINDOW_SRC = Path(__file__).parent.parent / "src" / "ui" / "main_window.py"

_QT_MAIN_THREAD_ONLY: frozenset[str] = frozenset(
    {
        "QTimer",
        "QObject",
        "QThread",
        "QApplication",
        "QWidget",
        "QDialog",
        "QMainWindow",
    }
)


def _parse() -> ast.Module:
    return ast.parse(_MAIN_WINDOW_SRC.read_text(encoding="utf-8"))


def _find_method(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef | None:
    """Return the AST node for ``class_name.method_name``, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    return None


def _qt_names_in_function(func_node: ast.FunctionDef) -> list[tuple[str, int]]:
    """Return (name, lineno) pairs for Qt main-thread-only names in *func_node*."""
    violations: list[tuple[str, int]] = []
    for child in ast.walk(func_node):
        if isinstance(child, ast.Name) and child.id in _QT_MAIN_THREAD_ONLY:
            violations.append((child.id, child.lineno))
    return violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_qtimer_in_worker_thread() -> None:
    """Daemon-thread ``_run`` bodies must not reference any main-thread Qt types.

    Walks every ``FunctionDef`` named ``_run`` in the source (the conventional
    inner function passed as ``threading.Thread(target=_run, …)`` in this
    codebase) and asserts zero references to main-thread-only Qt classes.
    """
    tree = _parse()
    violations: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_run":
            violations.extend(_qt_names_in_function(node))

    assert violations == [], (
        f"QTimer / main-thread-only Qt type(s) found inside daemon-thread _run "
        f"function(s) in {_MAIN_WINDOW_SRC.name}: {violations}"
    )


def test_spawn_feature_collection_single_call() -> None:
    """``_spawn_feature_collection`` must be called exactly once in ``_on_review_generate``."""
    tree = _parse()
    method = _find_method(tree, "MainWindow", "_on_review_generate")
    assert method is not None, "_on_review_generate not found on MainWindow"

    call_count = 0
    for node in ast.walk(method):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_spawn_feature_collection"
        ):
            call_count += 1

    assert call_count == 1, (
        f"Expected exactly 1 call to _spawn_feature_collection in "
        f"_on_review_generate, found {call_count} (D2 duplicate regression?)"
    )


def test_spawn_feature_collection_def_before_call() -> None:
    """``_spawn_feature_collection`` must be defined before it is called.

    Iterates over the *direct* body statements of ``_on_review_generate``
    in source order and asserts that the ``FunctionDef`` for
    ``_spawn_feature_collection`` appears at a lower index (earlier line)
    than any ``Expr`` call to it.
    """
    tree = _parse()
    method = _find_method(tree, "MainWindow", "_on_review_generate")
    assert method is not None, "_on_review_generate not found on MainWindow"

    def_lineno: int | None = None
    call_lineno: int | None = None

    for node in ast.walk(method):
        if isinstance(node, ast.FunctionDef) and node.name == "_spawn_feature_collection":
            def_lineno = node.lineno
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_spawn_feature_collection"
        ):
            call_lineno = node.lineno

    assert def_lineno is not None, (
        "_spawn_feature_collection FunctionDef not found in _on_review_generate"
    )
    assert call_lineno is not None, (
        "_spawn_feature_collection call not found in _on_review_generate"
    )
    assert def_lineno < call_lineno, (
        f"_spawn_feature_collection defined at line {def_lineno} but called at "
        f"line {call_lineno} — call-before-def would cause NameError at runtime"
    )
