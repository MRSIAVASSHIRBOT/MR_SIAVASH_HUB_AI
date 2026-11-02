from pathlib import Path

import pytest

from mrhub.nexus.static_analysis import (
    MAX_FILE_BYTES,
    MAX_FILES,
    StaticAnalysisError,
    analyze_python_repository,
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
