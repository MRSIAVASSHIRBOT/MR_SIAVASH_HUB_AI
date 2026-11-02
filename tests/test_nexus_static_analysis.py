from pathlib import Path

import pytest

from mrhub.nexus.static_analysis import (
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

