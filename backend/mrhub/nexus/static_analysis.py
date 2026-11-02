"""Read-only Python repository inventory and static checks; never imports or executes targets."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

MAX_FILES = 2_000
MAX_FILE_BYTES = 1_000_000
EXCLUDED_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
})


class StaticAnalysisError(ValueError):
    """Raised when the requested analysis root is not a valid directory."""


def analyze_python_repository(root: str | Path, *, max_files: int = MAX_FILES) -> dict[str, Any]:
    """Inventory Python files and emit line-specific defensive findings without source excerpts."""
    if not 1 <= max_files <= MAX_FILES:
        raise ValueError(f"max_files must be between 1 and {MAX_FILES}")
    requested_root = Path(root).expanduser()
    try:
        resolved_root = requested_root.resolve(strict=True)
    except OSError as exc:
        raise StaticAnalysisError("Analysis root does not exist") from exc
    if not resolved_root.is_dir():
        raise StaticAnalysisError("Analysis root must be a directory")

    inventory: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    scanned = 0
    skipped_large = 0
    truncated = False

    for current, directories, filenames in os.walk(resolved_root, followlinks=False):
        directories[:] = sorted(
            name for name in directories
            if name not in EXCLUDED_DIRS and not (Path(current) / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = Path(current) / filename
            if path.suffix != ".py" or path.is_symlink():
                continue
            if scanned >= max_files:
                truncated = True
                break
            try:
                relative = path.relative_to(resolved_root).as_posix()
                size = path.stat().st_size
                if size > MAX_FILE_BYTES:
                    skipped_large += 1
                    findings.append({
                        "rule_id": "PY000",
                        "severity": "info",
                        "path": relative,
                        "line": 1,
                        "message": "File skipped because it exceeds the analysis size limit.",
                    })
                    continue
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                findings.append({
                    "rule_id": "PY001",
                    "severity": "warning",
                    "path": str(path.relative_to(resolved_root)),
                    "line": 1,
                    "message": "File could not be read as UTF-8; contents were not exposed.",
                })
                continue

            scanned += 1
            try:
                tree = ast.parse(source, filename=relative)
            except SyntaxError as exc:
                findings.append({
                    "rule_id": "PY002",
                    "severity": "warning",
                    "path": relative,
                    "line": max(1, exc.lineno or 1),
                    "message": "Python syntax could not be parsed.",
                })
                inventory.append({"path": relative, "bytes": size, "parse_status": "syntax_error"})
                continue

            inventory.append({
                "path": relative,
                "bytes": size,
                "parse_status": "ok",
                "top_level_definitions": sum(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    for node in tree.body
                ),
            })
            findings.extend(_check_tree(tree, relative))
        if truncated:
            break

    findings.sort(key=lambda item: (item["path"], item["line"], item["rule_id"]))
    inventory.sort(key=lambda item: item["path"])
    return {
        "mode": "read_only_static_analysis",
        "root_label": resolved_root.name or ".",
        "files_scanned": scanned,
        "files_skipped_large": skipped_large,
        "truncated": truncated,
        "inventory": inventory,
        "findings": findings,
        "source_code_included": False,
        "targets_executed": False,
        "files_modified": False,
    }


def _check_tree(tree: ast.AST, relative: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(rule_id: str, node: ast.AST, severity: str, message: str) -> None:
        findings.append({
            "rule_id": rule_id,
            "severity": severity,
            "path": relative,
            "line": max(1, getattr(node, "lineno", 1)),
            "message": message,
        })

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            add("PY101", node, "high", "Dynamic code evaluation call requires manual security review.")
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in {"loads", "load"} and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "pickle":
                    add("PY102", node, "high", "Pickle deserialization can execute code; verify input trust.")
                if node.func.value.id == "yaml" and node.func.attr == "load":
                    safe_loader = any(
                        keyword.arg == "Loader"
                        and isinstance(keyword.value, ast.Attribute)
                        and isinstance(keyword.value.value, ast.Name)
                        and keyword.value.value.id == "yaml"
                        and keyword.value.attr == "SafeLoader"
                        for keyword in node.keywords
                    )
                    if not safe_loader:
                        add("PY103", node, "medium", "YAML load call lacks an explicit SafeLoader.")
            if node.func.attr in {"run", "Popen", "call", "check_call", "check_output"}:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                    shell_enabled = any(
                        keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                        for keyword in node.keywords
                    )
                    if shell_enabled:
                        add("PY104", node, "high", "Subprocess call enables shell=True.")
    return findings
