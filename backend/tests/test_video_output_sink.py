import pytest

from mrhub.media.repository import MediaAssetRepository


def _repository(tmp_path):
    repository = MediaAssetRepository(tmp_path / "media.sqlite")
    repository.tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    return repository


def test_bounded_sink_commit(tmp_path):
    repository = _repository(tmp_path)
    _asset_id, storage_key, target = repository.new_output_target()
    with repository.create_output_sink(storage_key, max_bytes=32) as sink:
        assert sink.write(b"first-") == 6
        assert sink.write(memoryview(b"second")) == 6
        assert target.exists() is False
        committed = sink.commit()
    assert committed == target
    assert target.read_bytes() == b"first-second"


def test_bounded_sink_rejects_limit_and_cleans_partial_file(tmp_path):
    repository = _repository(tmp_path)
    _asset_id, storage_key, target = repository.new_output_target()
    with (
        pytest.raises(ValueError, match="byte limit"),
        repository.create_output_sink(storage_key, max_bytes=5) as sink,
    ):
        sink.write(b"12345")
        sink.write(b"6")
    assert target.exists() is False
    assert not list(repository.storage_root.glob("*.output-part"))


def test_bounded_sink_rejects_empty_commit_and_existing_target(tmp_path):
    repository = _repository(tmp_path)
    _asset_id, storage_key, target = repository.new_output_target()
    with (
        pytest.raises(ValueError, match="empty"),
        repository.create_output_sink(storage_key, max_bytes=10) as sink,
    ):
        sink.commit()
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        repository.create_output_sink(storage_key, max_bytes=10)


def test_overflow_poison_sink_even_when_exception_is_caught(tmp_path):
    repository = _repository(tmp_path)
    _asset_id, storage_key, target = repository.new_output_target()

    with repository.create_output_sink(storage_key, max_bytes=5) as sink:
        assert sink.write(b"12345") == 5
        with pytest.raises(ValueError, match="byte limit"):
            sink.write(b"6")

        assert sink.bytes_written == 5
        with pytest.raises(ValueError, match="cannot be committed"):
            sink.commit()
        with pytest.raises(ValueError, match="closed"):
            sink.write(b"7")

    assert target.exists() is False
    assert not list(repository.storage_root.glob(".*.output-part"))
