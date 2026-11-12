"""Read-only Python repository inventory and static checks; never imports or executes targets."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

MAX_FILES = 2_000
MAX_FILE_BYTES = 1_000_000
MAX_SOURCE_CHARS = 64_000

RULE_GUIDANCE: dict[str, tuple[str, str]] = {
    "PY000": (
        "high",
        "Reduce the file size or split the module before running deeper analysis.",
    ),
    "PY001": (
        "high",
        "Review file encoding and access permissions; keep source contents out of diagnostics.",
    ),
    "PY002": (
        "high",
        "Correct the syntax error, then rerun the read-only analysis.",
    ),
    "PY003": (
        "medium",
        "Review directory permissions and explicit analysis scope, then rerun the inventory.",
    ),
    "PY101": (
        "high",
        "Replace eval/exec with a typed parser or explicit allow-listed dispatch and validate inputs.",
    ),
    "PY102": (
        "high",
        "Avoid pickle for untrusted data; use a non-executable format such as JSON with a schema.",
    ),
    "PY103": (
        "high",
        "Use yaml.safe_load or pass yaml.SafeLoader explicitly.",
    ),
    "PY104": (
        "high",
        "Pass subprocess arguments as a list with shell=False and validate each argument.",
    ),
    "PY105": (
        "high",
        "Avoid os.system/os.popen for untrusted input; use a bounded argument-list subprocess call.",
    ),
    "PY106": (
        "high",
        "Keep TLS certificate verification enabled; configure a trusted CA bundle instead of disabling verification.",
    ),
}
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
    examined = 0
    skipped_large = 0
    truncated = False

    def report_walk_error(error: OSError) -> None:
        nonlocal truncated
        truncated = True
        error_path = Path(error.filename) if error.filename else resolved_root
        try:
            relative = error_path.relative_to(resolved_root).as_posix()
        except ValueError:
            relative = "."
        findings.append(_finding(
            "PY003",
            "warning",
            relative or ".",
            1,
            "Directory could not be traversed; repository inventory is incomplete.",
        ))

    for current, directories, filenames in os.walk(
        resolved_root,
        followlinks=False,
        onerror=report_walk_error,
    ):
        directories[:] = sorted(
            name for name in directories
            if name not in EXCLUDED_DIRS and not (Path(current) / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = Path(current) / filename
            if path.suffix != ".py" or path.is_symlink():
                continue
            if examined >= max_files:
                truncated = True
                break
            examined += 1
            try:
                relative = path.relative_to(resolved_root).as_posix()
                size = path.stat().st_size
                if size > MAX_FILE_BYTES:
                    skipped_large += 1
                    findings.append(_finding(
                        "PY000",
                        "info",
                        relative,
                        1,
                        "File skipped because it exceeds the analysis size limit.",
                    ))
                    continue
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                findings.append(_finding(
                    "PY001",
                    "warning",
                    str(path.relative_to(resolved_root)),
                    1,
                    "File could not be read as UTF-8; contents were not exposed.",
                ))
                continue

            scanned += 1
            try:
                tree = ast.parse(source, filename=relative)
            except SyntaxError as exc:
                findings.append(_finding(
                    "PY002",
                    "warning",
                    relative,
                    max(1, exc.lineno or 1),
                    "Python syntax could not be parsed.",
                ))
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
        "files_examined": examined,
        "files_skipped_large": skipped_large,
        "truncated": truncated,
        "inventory": inventory,
        "findings": findings,
        "source_code_included": False,
        "targets_executed": False,
        "files_modified": False,
    }


def _finding(
    rule_id: str,
    severity: str,
    path: str,
    line: int,
    message: str,
) -> dict[str, Any]:
    confidence, remediation = RULE_GUIDANCE.get(
        rule_id,
        ("medium", "Review the evidence manually and apply a minimal, tested remediation."),
    )
    return {
        "rule_id": rule_id,
        "severity": severity,
        "confidence": confidence,
        "path": path,
        "line": max(1, line),
        "message": message,
        "remediation": remediation,
    }


def analyze_python_source(source: str, *, path: str = "proposed.py") -> dict[str, Any]:
    """Analyze supplied Python text only; never reads paths or executes source."""
    if not isinstance(source, str) or len(source) > MAX_SOURCE_CHARS:
        raise ValueError("source_too_large")
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError) as exc:
        finding = _finding(
            "PY002",
            "warning",
            path,
            max(1, getattr(exc, "lineno", None) or 1),
            "Python syntax could not be parsed.",
        )
        return {
            "status": "syntax_error",
            "findings": [finding],
            "source_code_included": False,
            "code_executed": False,
        }
    return {
        "status": "ok",
        "findings": _check_tree(tree, path),
        "source_code_included": False,
        "code_executed": False,
    }


def _check_tree(tree: ast.AST, relative: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    tracked_modules = {"pickle", "yaml", "subprocess", "os", "builtins", "requests", "httpx"}
    module_aliases: dict[str, set[str]] = {name: {name} for name in tracked_modules}
    risky_imports = {
        "pickle": {"loads", "load"},
        "yaml": {"load"},
        "subprocess": {"run", "Popen", "call", "check_call", "check_output"},
        "os": {"system", "popen"},
        "builtins": {"eval", "exec"},
        "requests": {"Session", "request", "get", "post", "put", "patch", "delete", "head", "options"},
        "httpx": {"Client", "AsyncClient", "request", "get", "post", "put", "patch", "delete", "head", "options"},
    }
    imported_calls: dict[str, set[str]] = {name: set() for name in tracked_modules}
    safe_loader_names = {"SafeLoader"}
    http_client_imports: dict[str, str] = {}

    # Resolve straightforward import aliases so common defensive checks do not
    # disappear merely because a module or imported function was renamed.
    for imported in ast.walk(tree):
        if isinstance(imported, ast.Import):
            for alias in imported.names:
                if alias.name in tracked_modules:
                    module_aliases[alias.name].add(alias.asname or alias.name)
        elif isinstance(imported, ast.ImportFrom) and imported.module in tracked_modules:
            module = imported.module
            for alias in imported.names:
                local_name = alias.asname or alias.name
                if module == "yaml" and alias.name == "SafeLoader":
                    safe_loader_names.add(local_name)
                if alias.name in risky_imports[module]:
                    imported_calls[module].add(local_name)
                if module == "requests" and alias.name == "Session":
                    http_client_imports[local_name] = "requests"
                elif module == "httpx" and alias.name in {"Client", "AsyncClient"}:
                    http_client_imports[local_name] = "httpx"

    def add(rule_id: str, node: ast.AST, severity: str, message: str) -> None:
        findings.append(_finding(
            rule_id,
            severity,
            relative,
            max(1, getattr(node, "lineno", 1)),
            message,
        ))

    def root_module_name(expression: ast.AST) -> str | None:
        # Resolve direct module calls and chained clients such as
        # requests.Session().get(...) without evaluating any target expression.
        while isinstance(expression, (ast.Attribute, ast.Call)):
            expression = expression.value if isinstance(expression, ast.Attribute) else expression.func
        return expression.id if isinstance(expression, ast.Name) else None

    def target_names(target: ast.AST) -> set[str]:
        if isinstance(target, ast.Name):
            return {target.id}
        if isinstance(target, (ast.Tuple, ast.List)):
            return {item.id for item in target.elts if isinstance(item, ast.Name)}
        return set()

    def client_constructor_module(value: ast.AST) -> str | None:
        if not isinstance(value, ast.Call):
            return None
        if isinstance(value.func, ast.Name):
            return http_client_imports.get(value.func.id)
        if isinstance(value.func, ast.Attribute):
            module_name = root_module_name(value.func.value)
            if module_name in module_aliases["requests"] and value.func.attr == "Session":
                return "requests"
            if module_name in module_aliases["httpx"] and value.func.attr in {"Client", "AsyncClient"}:
                return "httpx"
        return None

    # Track only simple assignments within their lexical scope. This avoids
    # treating an unrelated local variable with the same name in another
    # function as an HTTP client. It is not full Python data-flow analysis.
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def lexical_scope(node: ast.AST) -> ast.AST:
        current = node
        while current in parents:
            current = parents[current]
            if isinstance(current, (
                ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef
            )):
                return current
        return tree

    client_aliases: dict[tuple[ast.AST, str], list[tuple[int, str | None]]] = {}
    assignments = sorted(
        (
            item for item in ast.walk(tree)
            if isinstance(item, (ast.Assign, ast.AnnAssign))
        ),
        key=lambda item: (
            getattr(item, "lineno", 0),
            getattr(item, "col_offset", 0),
        ),
    )

    def client_module_at(scope: ast.AST, name: str, line: int) -> str | None:
        history = client_aliases.get((scope, name), ())
        for assigned_line, module in reversed(history):
            if assigned_line <= line:
                return module
        return None

    # Preserve simple local aliases (including alias chains), while recording
    # non-client reassignments as None so stale client identities are dropped.
    for assignment in assignments:
        value = assignment.value
        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        scope = lexical_scope(assignment)
        line = getattr(assignment, "lineno", 0)
        module = client_constructor_module(value) if value is not None else None
        if module is None and isinstance(value, ast.Name):
            module = client_module_at(scope, value.id, line)
        for target in targets:
            for name in target_names(target):
                client_aliases.setdefault((scope, name), []).append((line, module))

    for assignment in assignments:
        targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        value = assignment.value
        if not (
            isinstance(value, ast.Constant)
            and value.value is False
        ):
            continue
        scope = lexical_scope(assignment)
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "verify"
                and isinstance(target.value, ast.Name)
                and client_module_at(scope, target.value.id, getattr(assignment, "lineno", 0)) in {"requests", "httpx"}
            ):
                add(
                    "PY106",
                    assignment,
                    "high",
                    "HTTP client instance explicitly disables TLS certificate verification.",
                )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            called_name = node.func.id
            if called_name in {"eval", "exec"} or called_name in imported_calls["builtins"]:
                add("PY101", node, "high", "Dynamic code evaluation call requires manual security review.")
                continue
            for module in ("pickle", "yaml", "subprocess", "os", "requests", "httpx"):
                if called_name not in imported_calls[module]:
                    continue
                if module == "pickle":
                    add("PY102", node, "high", "Pickle deserialization can execute code; verify input trust.")
                elif module == "yaml":
                    safe_loader = any(
                        keyword.arg == "Loader"
                        and (
                            isinstance(keyword.value, ast.Name)
                            and keyword.value.id in safe_loader_names
                            or isinstance(keyword.value, ast.Attribute)
                            and isinstance(keyword.value.value, ast.Name)
                            and keyword.value.value.id in module_aliases["yaml"]
                            and keyword.value.attr == "SafeLoader"
                        )
                        for keyword in node.keywords
                    )
                    if not safe_loader:
                        add("PY103", node, "medium", "YAML load call lacks an explicit SafeLoader.")
                elif module == "subprocess":
                    if any(
                        keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                        for keyword in node.keywords
                    ):
                        add("PY104", node, "high", "Subprocess call enables shell=True.")
                elif module == "os":
                    add("PY105", node, "high", "OS shell command API requires manual security review.")
                elif module in {"requests", "httpx"} and any(
                    keyword.arg == "verify"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                    for keyword in node.keywords
                ):
                    add("PY106", node, "high", "HTTP client explicitly disables TLS certificate verification.")
            continue

        if not isinstance(node.func, ast.Attribute):
            continue

        module_name = root_module_name(node.func.value)
        function_name = node.func.attr

        if module_name in module_aliases["builtins"] and function_name in {"eval", "exec"}:
            add("PY101", node, "high", "Dynamic code evaluation call requires manual security review.")

        if module_name in module_aliases["pickle"] and function_name in {"loads", "load"}:
            add("PY102", node, "high", "Pickle deserialization can execute code; verify input trust.")

        if module_name in module_aliases["yaml"] and function_name == "load":
            safe_loader = any(
                keyword.arg == "Loader"
                and (
                    isinstance(keyword.value, ast.Name)
                    and keyword.value.id in safe_loader_names
                    or isinstance(keyword.value, ast.Attribute)
                    and isinstance(keyword.value.value, ast.Name)
                    and keyword.value.value.id in module_aliases["yaml"]
                    and keyword.value.attr == "SafeLoader"
                )
                for keyword in node.keywords
            )
            if not safe_loader:
                add("PY103", node, "medium", "YAML load call lacks an explicit SafeLoader.")

        if module_name in module_aliases["subprocess"] and function_name in risky_imports["subprocess"]:
            shell_enabled = any(
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
            if shell_enabled:
                add("PY104", node, "high", "Subprocess call enables shell=True.")

        if module_name in module_aliases["os"] and function_name in {"system", "popen"}:
            add("PY105", node, "high", "OS shell command API requires manual security review.")

        direct_client_module = next(
            (
                module for module in ("requests", "httpx")
                if module_name in module_aliases[module]
            ),
            None,
        )
        client_modules = (
            {direct_client_module}
            if direct_client_module is not None
            else (
                {client_module_at(lexical_scope(node), module_name, getattr(node, "lineno", 0))}
                if client_module_at(lexical_scope(node), module_name, getattr(node, "lineno", 0)) is not None
                else set()
            )
        )

        if (
            any(function_name in risky_imports[module] for module in client_modules)
            and any(
                keyword.arg == "verify"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is False
                for keyword in node.keywords
            )
        ):
            add("PY106", node, "high", "HTTP client explicitly disables TLS certificate verification.")

    return findings
