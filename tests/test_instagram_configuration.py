from pydantic import SecretStr

from mrhub.config import Settings
from mrhub.content.providers import (
    InstagramGraphImageAdapter,
    TelegramBotApiAdapter,
    configured_publish_adapters,
)


def test_instagram_adapter_is_not_registered_without_complete_credentials():
    adapters = configured_publish_adapters(Settings())
    assert adapters == {}


def test_instagram_adapter_registers_only_when_all_instagram_settings_exist():
    config = Settings(
        instagram_access_token=SecretStr("test-token"),
        instagram_user_id="17841400000000000",
        instagram_graph_api_version="v24.0",
    )
    adapters = configured_publish_adapters(config)

    assert isinstance(adapters["instagram"], InstagramGraphImageAdapter)
    assert "telegram" not in adapters


def test_telegram_and_instagram_adapters_can_be_configured_independently():
    telegram_only = configured_publish_adapters(
        Settings(
            telegram_bot_token=SecretStr("telegram-test-token"),
            telegram_chat_id="@test-channel",
        )
    )
    instagram_only = configured_publish_adapters(
        Settings(
            instagram_access_token=SecretStr("instagram-test-token"),
            instagram_user_id="17841400000000000",
            instagram_graph_api_version="v24.0",
        )
    )

    assert isinstance(telegram_only["telegram"], TelegramBotApiAdapter)
    assert "instagram" not in telegram_only
    assert isinstance(instagram_only["instagram"], InstagramGraphImageAdapter)
    assert "telegram" not in instagram_only


def test_partial_instagram_configuration_fails_closed():
    config = Settings(
        instagram_access_token=SecretStr("test-token"),
        instagram_user_id="17841400000000000",
    )

    assert "instagram" not in configured_publish_adapters(config)
