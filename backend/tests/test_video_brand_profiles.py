import sqlite3
from uuid import UUID

import pytest

from mrhub.video_intelligence.repository import VideoBrandRepository
from mrhub.video_intelligence.schemas import BrandIdentity


def _repository(tmp_path):
    repository = VideoBrandRepository(tmp_path / "video-brands.sqlite")
    repository.tasks.create_auth_user("owner-a", "owner-a", "salt-a", "hash-a")
    repository.tasks.create_auth_user("owner-b", "owner-b", "salt-b", "hash-b")
    return repository


def _brand(name: str = "MR SIAVASH") -> BrandIdentity:
    return BrandIdentity(
        brand_name=name,
        handle="@mr_siavash_ir_bot",
        colors=["#071A12", "#00C878"],
        font_preferences=["Vazirmatn"],
        tone="Cinematic, precise, educational",
    )


def test_brand_profiles_are_private_and_support_crud(tmp_path):
    repository = _repository(tmp_path)
    created = repository.create("owner-a", _brand())

    assert created["brand_name"] == "MR SIAVASH"
    assert created["colors"] == ["#071A12", "#00C878"]
    assert len(repository.list("owner-a")) == 1
    assert repository.list("owner-b") == []

    profile_id = UUID(str(created["profile_id"]))
    assert repository.get("owner-b", profile_id) is None
    assert repository.update("owner-b", profile_id, _brand("Other")) is None
    assert repository.delete("owner-b", profile_id) is False

    updated = repository.update("owner-a", profile_id, _brand("MR SIAVASH Studio"))
    assert updated is not None
    assert updated["brand_name"] == "MR SIAVASH Studio"
    assert repository.delete("owner-a", profile_id) is True
    assert repository.get("owner-a", profile_id) is None


def test_brand_name_is_unique_per_owner(tmp_path):
    repository = _repository(tmp_path)
    repository.create("owner-a", _brand())

    with pytest.raises(sqlite3.IntegrityError):
        repository.create("owner-a", _brand())

    other_owner_profile = repository.create("owner-b", _brand())
    assert other_owner_profile["brand_name"] == "MR SIAVASH"
