import pytest

from client_helpers import authenticated_client
from mrhub.nexus.patch_proposals import (
    MAX_SOURCE_CHARS,
    PatchProposalError,
    create_patch_proposal,
)


def test_patch_proposal_returns_reviewable_diff_and_syntax_status():
    original = "def greet():\n    return 'hello'\n"
    proposed = "def greet(name='world'):\n    return f'hello {name}'\n"

    result = create_patch_proposal("src/greet.py", original, proposed)

    assert result["changed"] is True
    assert result["base_syntax"]["status"] == "ok"
    assert result["proposed_syntax"]["status"] == "ok"
    assert "--- a/src/greet.py" in result["diff"]
    assert "+++ b/src/greet.py" in result["diff"]
    assert "return f'hello {name}'" in result["diff"]
    assert result["source_stored"] is False
    assert result["proposal_persisted"] is False
    assert result["code_executed"] is False
    assert result["files_modified"] is False
    assert len(result["base_sha256"]) == 64
    assert len(result["proposed_sha256"]) == 64
    assert result["static_review"]["status"] == "complete"
    assert result["static_review"]["human_review_required"] is True
    assert result["static_review"]["code_executed"] is False


def test_patch_proposal_flags_syntax_errors_without_executing_source():
    result = create_patch_proposal(
        "module.py",
        "def safe():\n    return 1\n",
        "def broken(:\n    return 2\n",
    )

    assert result["proposed_syntax"]["status"] == "syntax_error"
    assert result["proposed_syntax"]["line"] == 1
    assert result["code_executed"] is False


@pytest.mark.parametrize(
    "path",
    ["../secret.py", "/tmp/secret.py", "folder\\secret.py", "notes.txt"],
)
def test_patch_proposal_rejects_unsafe_or_non_python_path_labels(path: str):
    with pytest.raises(PatchProposalError):
        create_patch_proposal(path, "x = 1\n", "x = 2\n")


def test_patch_proposal_bounds_source_size():
    source = "x = 1\n" * (MAX_SOURCE_CHARS // 6 + 2)
    with pytest.raises(PatchProposalError, match="source_too_large"):
        create_patch_proposal("module.py", source, "x = 2\n")


def test_authenticated_patch_proposal_api_returns_diff_without_applying_it():
    client = authenticated_client()
    response = client.post(
        "/nexus/patch-proposals",
        json={
            "path": "src/example.py",
            "original_source": "def answer():\n    return 41\n",
            "proposed_source": "def answer():\n    return 42\n",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["changed"] is True
    assert "return 42" in result["diff"]
    assert result["files_modified"] is False
    assert result["code_executed"] is False
    assert result["proposal_persisted"] is False
    assert result["static_review"]["status"] == "complete"



def test_patch_proposal_handles_null_byte_source_as_syntax_error():
    result = create_patch_proposal(
        "module.py",
        "x = 1\n",
        "x = \x00\n",
    )

    assert result["proposed_syntax"]["status"] == "syntax_error"
    assert result["proposed_syntax"]["line"] == 1



def test_patch_review_identifies_new_high_confidence_risk_without_running_code():
    result = create_patch_proposal(
        "src/parser.py",
        "def parse(value):\n    return value\n",
        "def parse(value):\n    return eval(value)\n",
    )

    review = result["static_review"]
    assert review["status"] == "complete"
    assert review["introduced_high_severity_count"] == 1
    assert len(review["introduced_findings"]) == 1
    finding = review["introduced_findings"][0]
    assert finding["rule_id"] == "PY101"
    assert finding["confidence"] == "high"
    assert finding["line"] == 2
    assert "typed parser" in finding["remediation"]
    assert review["code_executed"] is False
    assert result["files_modified"] is False


def test_patch_review_reports_resolved_findings_without_auto_approving():
    result = create_patch_proposal(
        "src/parser.py",
        "def parse(value):\n    return eval(value)\n",
        "def parse(value):\n    return value\n",
    )

    review = result["static_review"]
    assert review["introduced_findings"] == []
    assert len(review["resolved_findings"]) == 1
    assert review["resolved_findings"][0]["rule_id"] == "PY101"
    assert review["human_review_required"] is True


def test_patch_review_marks_comparison_partial_when_proposed_source_has_syntax_error():
    result = create_patch_proposal(
        "src/parser.py",
        "def parse(value):\n    return value\n",
        "def parse(:\n    return value\n",
    )

    review = result["static_review"]
    assert review["status"] == "partial"
    assert result["proposed_syntax"]["status"] == "syntax_error"
    assert any(item["rule_id"] == "PY002" for item in review["proposed_findings"])
    assert review["human_review_required"] is True



def test_authenticated_patch_proposal_api_exposes_new_static_risks():
    client = authenticated_client()
    response = client.post(
        "/nexus/patch-proposals",
        json={
            "path": "src/parser.py",
            "original_source": "def parse(value):\n    return value\n",
            "proposed_source": "def parse(value):\n    return eval(value)\n",
        },
    )

    assert response.status_code == 200
    review = response.json()["static_review"]
    assert review["human_review_required"] is True
    assert review["introduced_high_severity_count"] == 1
    assert review["introduced_findings"][0]["rule_id"] == "PY101"
    assert review["introduced_findings"][0]["confidence"] == "high"
    assert response.json()["code_executed"] is False
    assert response.json()["files_modified"] is False
