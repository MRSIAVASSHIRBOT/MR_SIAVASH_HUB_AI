import pytest

from mrhub.content.resource_reply import build_optional_support_resource_reply


def test_resource_reply_places_optional_follow_and_share_cta_before_unconditional_link():
    url = "https://example.org/learning/account-security"
    message = build_optional_support_resource_reply(url)

    follow_position = message.index("دنبال کنی")
    share_position = message.index("برای دوستانت هم بفرستی")
    resource_position = message.index(url)

    assert follow_position < resource_position
    assert share_position < resource_position
    assert "کاملاً اختیاریه" in message
    assert "نیازی به فالو یا اشتراک‌گذاری نیست" in message
    assert message.endswith(url)


def test_resource_reply_does_not_accept_or_depend_on_follow_or_share_state():
    # The API intentionally has no follower/share-state parameters.
    message = build_optional_support_resource_reply("https://example.org/free-guide")
    assert "https://example.org/free-guide" in message


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://example.org/guide",
        "javascript:alert(1)",
        "//example.org/guide",
        "https://user:password@example.org/guide",
        "https://example.org/a guide",
        "https://example.org:invalid/guide",
        "https://example.org:65536/guide",
    ],
)
def test_resource_reply_rejects_non_https_or_malformed_urls(url):
    with pytest.raises(ValueError):
        build_optional_support_resource_reply(url)


@pytest.mark.parametrize("label", ["", "two\nlines", "two\rlines"])
def test_resource_reply_rejects_invalid_resource_labels(label):
    with pytest.raises(ValueError):
        build_optional_support_resource_reply(
            "https://example.org/guide",
            resource_label=label,
        )
