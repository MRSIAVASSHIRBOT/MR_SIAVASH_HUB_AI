from pathlib import Path

import pytest

from mrhub.nexus.static_analysis import (
    MAX_FILE_BYTES,
    MAX_FILES,
    StaticAnalysisError,
    analyze_python_repository,
    analyze_python_source,
)


def test_static_analysis_reports_line_evidence_without_source_text(tmp_path: Path):
    (tmp_path / "module.py").write_text(
        "def run(user_input):\n    return eval(user_input)\n",
        encoding="utf-8",
    )
    result = analyze_python_repository(tmp_path)

    assert result["mode"] == "read_only_static_analysis"
    assert result["files_scanned"] == 1
    assert result["targets_executed"] is False
    assert result["files_modified"] is False
    finding = next(item for item in result["findings"] if item["rule_id"] == "PY101")
    assert finding["path"] == "module.py"
    assert finding["line"] == 2
    assert finding["confidence"] == "high"
    assert "typed parser" in finding["remediation"]
    assert "user_input" not in str(result)


def test_static_analysis_skips_generated_directories_and_non_python_files(tmp_path: Path):
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("eval('x')", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("eval('x')", encoding="utf-8")
    (tmp_path / "safe.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

    result = analyze_python_repository(tmp_path)

    assert result["files_scanned"] == 1
    assert [item["path"] for item in result["inventory"]] == ["safe.py"]
    assert result["findings"] == []


def test_static_analysis_reports_multiple_defensive_patterns(tmp_path: Path):
    (tmp_path / "unsafe.py").write_text(
        "import subprocess\nimport pickle\n\n"
        "def load(data):\n    pickle.loads(data)\n"
        "    subprocess.run('echo hi', shell=True)\n",
        encoding="utf-8",
    )
    result = analyze_python_repository(tmp_path)
    rules = {item["rule_id"] for item in result["findings"]}

    assert {"PY102", "PY104"} <= rules


def test_static_analysis_rejects_invalid_root_and_limits(tmp_path: Path):
    with pytest.raises(StaticAnalysisError):
        analyze_python_repository(tmp_path / "missing")
    not_a_dir = tmp_path / "not-a-dir.txt"
    not_a_dir.write_text("x", encoding="utf-8")
    with pytest.raises(StaticAnalysisError):
        analyze_python_repository(not_a_dir)
    with pytest.raises(ValueError):
        analyze_python_repository(tmp_path, max_files=MAX_FILES + 1)


def test_static_analysis_marks_inventory_truncated_at_file_budget(tmp_path: Path):
    (tmp_path / "a.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("value = 3\n", encoding="utf-8")

    result = analyze_python_repository(tmp_path, max_files=1)

    assert result["files_scanned"] == 1
    assert result["truncated"] is True
    assert len(result["inventory"]) == 1
    assert result["source_code_included"] is False
    assert result["targets_executed"] is False
    assert result["files_modified"] is False


def test_static_analysis_counts_oversized_candidates_against_file_budget(tmp_path: Path):
    (tmp_path / "a-large.py").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    (tmp_path / "b-small.py").write_text("value = 1\n", encoding="utf-8")

    result = analyze_python_repository(tmp_path, max_files=1)

    assert result["files_examined"] == 1
    assert result["files_scanned"] == 0
    assert result["files_skipped_large"] == 1
    assert result["truncated"] is True
    assert result["inventory"] == []
    assert result["source_code_included"] is False
    assert result["targets_executed"] is False
    assert result["files_modified"] is False


def test_static_analysis_marks_inventory_incomplete_when_directory_walk_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from mrhub.nexus import static_analysis

    blocked_directory = tmp_path / "restricted"

    def failing_walk(root, *, followlinks, onerror):
        onerror(PermissionError(13, "permission denied", str(blocked_directory)))
        yield str(root), [], ["visible.py"]

    (tmp_path / "visible.py").write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(static_analysis.os, "walk", failing_walk)

    result = analyze_python_repository(tmp_path)

    assert result["files_scanned"] == 1
    assert result["truncated"] is True
    finding = next(item for item in result["findings"] if item["rule_id"] == "PY003")
    assert finding["path"] == "restricted"
    assert finding["severity"] == "warning"
    assert "incomplete" in finding["message"]



def test_source_analysis_reports_confidence_and_remediation_without_execution():
    result = analyze_python_source(
        "def parse(value):\n    return eval(value)\n",
        path="src/parser.py",
    )

    assert result["status"] == "ok"
    assert result["code_executed"] is False
    assert result["source_code_included"] is False
    finding = result["findings"][0]
    assert finding["rule_id"] == "PY101"
    assert finding["path"] == "src/parser.py"
    assert finding["line"] == 2
    assert finding["confidence"] == "high"
    assert "typed parser" in finding["remediation"]


def test_static_analysis_detects_common_import_aliases_and_os_shell_apis():
    source = """import pickle as serializer
from subprocess import run as run_command
import os as operating_system
from yaml import load as parse_yaml
from yaml import SafeLoader as SafeYamlLoader
serializer.loads(payload)
run_command(command, shell=True)
operating_system.system(command)
parse_yaml(document)
parse_yaml(document, Loader=SafeYamlLoader)
"""
    result = analyze_python_source(source, path="src/aliased_imports.py")

    rules = [item["rule_id"] for item in result["findings"]]
    assert rules.count("PY102") == 1
    assert rules.count("PY103") == 1
    assert rules.count("PY104") == 1
    assert rules.count("PY105") == 1
    assert result["code_executed"] is False
    assert result["source_code_included"] is False


def test_static_analysis_detects_os_system_and_os_popen_without_aliases():
    result = analyze_python_source(
        "import os\nos.system(command)\nos.popen(command)\n",
        path="src/os_shell.py",
    )

    assert [item["rule_id"] for item in result["findings"]] == ["PY105", "PY105"]


def test_static_analysis_detects_requests_tls_verification_disabled_and_import_aliases():
    result = analyze_python_source(
        "import requests as http\n"
        "from requests import post as send\n"
        "http.get(url, verify=False)\n"
        "send(url, verify=False)\n"
        "http.get(secure_url, verify=True)\n",
        path="src/http_client.py",
    )

    findings = [item for item in result["findings"] if item["rule_id"] == "PY106"]
    assert len(findings) == 2
    assert [item["line"] for item in findings] == [3, 4]
    assert all(item["severity"] == "high" for item in findings)
    assert all("TLS certificate verification" in item["message"] for item in findings)
    assert result["code_executed"] is False
    assert result["source_code_included"] is False


def test_static_analysis_detects_httpx_tls_verification_disabled_and_client_aliases():
    result = analyze_python_source(
        "import httpx as client\n"
        "from httpx import AsyncClient as AsyncHTTP\n"
        "client.get(url, verify=False)\n"
        "AsyncHTTP(verify=False)\n"
        "client.get(secure_url, verify=True)\n",
        path="src/httpx_client.py",
    )

    findings = [item for item in result["findings"] if item["rule_id"] == "PY106"]
    assert len(findings) == 2
    assert [item["line"] for item in findings] == [3, 4]
    assert all(item["severity"] == "high" for item in findings)
    assert result["code_executed"] is False
    assert result["source_code_included"] is False



def test_static_analysis_detects_tls_disabled_on_chained_requests_session_calls():
    result = analyze_python_source(
        "import requests as http\n"
        "http.Session().get(url, verify=False)\n"
        "http.Session().get(secure_url, verify=True)\n",
        path="src/requests_session.py",
    )

    findings = [item for item in result["findings"] if item["rule_id"] == "PY106"]
    assert len(findings) == 1
    assert findings[0]["line"] == 2
    assert findings[0]["severity"] == "high"
    assert result["code_executed"] is False
    assert result["source_code_included"] is False


def test_static_analysis_detects_tls_disabled_on_chained_httpx_client_calls():
    result = analyze_python_source(
        "import httpx as transport\n"
        "transport.Client().get(url, verify=False)\n"
        "transport.AsyncClient().post(url, verify=False)\n"
        "transport.Client().get(secure_url, verify=True)\n",
        path="src/httpx_client_session.py",
    )

    findings = [item for item in result["findings"] if item["rule_id"] == "PY106"]
    assert len(findings) == 2
    assert [item["line"] for item in findings] == [2, 3]
    assert all(item["severity"] == "high" for item in findings)
    assert result["code_executed"] is False
    assert result["source_code_included"] is False



def test_static_analysis_detects_tls_disabled_on_http_client_instance_assignments_and_calls():
    result = analyze_python_source(
        "import requests as http\n"
        "from httpx import AsyncClient as AsyncHTTP\n"
        "session = http.Session()\n"
        "session.verify = False\n"
        "client = AsyncHTTP()\n"
        "client.verify = False\n"
        "client.get(url, verify=False)\n"
        "safe = object()\n"
        "safe.verify = False\n"
        "session.verify = True\n",
        path="src/http_client_instance.py",
    )

    findings = [item for item in result["findings"] if item["rule_id"] == "PY106"]
    assert [item["line"] for item in findings] == [4, 6, 7]
    assert all(item["severity"] == "high" for item in findings)
    assert result["code_executed"] is False
    assert result["source_code_included"] is False



def test_static_analysis_preserves_client_alias_evidence_across_function_scopes():
    result = analyze_python_source(
        "import httpx\n"
        "def unsafe_request():\n"
        "    client = httpx.Client()\n"
        "    client.get(url, verify=False)\n"
        "def unrelated_scope():\n"
        "    client = object()\n",
        path="src/client_scope_reuse.py",
    )

    findings = [item for item in result["findings"] if item["rule_id"] == "PY106"]
    assert [item["line"] for item in findings] == [4]
    assert result["code_executed"] is False
    assert result["source_code_included"] is False
