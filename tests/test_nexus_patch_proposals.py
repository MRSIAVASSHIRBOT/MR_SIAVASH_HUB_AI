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



def test_patch_proposal_handles_null_byte_source_as_syntax_error():
    result = create_patch_proposal(
        "module.py",
        "x = 1\n",
        "x = \x00\n",
    )

    assert result["proposed_syntax"]["status"] == "syntax_error"
    assert result["proposed_syntax"]["line"] == 1
