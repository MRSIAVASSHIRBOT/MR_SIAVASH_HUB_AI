import pytest

from mrhub.content.resource_reply import build_optional_support_resource_reply


def test_resource_reply_places_optional_follow_and_share_cta_before_unconditional_link():
    url = "https://example.org/learning/account-security"
    message = build_optional_support_resource_reply(url)

    follow_position = message.index("دنبال کنی")
    share_position = message.index("برای دوستانت بفرست")
    resource_position = message.index(url)

    assert follow_position < resource_position
    assert share_position < resource_position
    assert "کاملاً اختیاریه" in message
    assert "نیازی به فالو یا اشتراک‌گذاری نیست" in message
    assert message.endswith(url)


def test_resource_reply_support_copy_can_be_customized():
    message = build_optional_support_resource_reply(
        "https://example.org/guide",
        resource_label="راهنمای امنیت حساب",
        intro_text="درود!",
        follow_cta_text="صفحه را دنبال کن.",
        share_cta_text="این آموزش را بفرست.",
    )
    assert message.startswith("درود!")
    assert "صفحه را دنبال کن." in message
    assert "این آموزش را بفرست." in message
    assert "راهنمای امنیت حساب" in message


def test_resource_reply_always_includes_link_when_both_ctas_are_disabled():
    url = "https://example.org/free-guide"
    message = build_optional_support_resource_reply(
        url,
        include_follow=False,
        include_share=False,
    )
    assert message == "سلام! ✨\n\n📚 لینک دریافت محتوای آموزشی:\n" + url
    assert "دنبال کنی" not in message
    assert "برای دوستانت بفرست" not in message


def test_resource_reply_does_not_accept_or_depend_on_follow_or_share_state():
    # The builder has no follower/share-state inputs by design.
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


def test_resource_reply_requires_text_for_enabled_ctas():
    with pytest.raises(ValueError):
        build_optional_support_resource_reply(
            "https://example.org/guide",
            include_follow=True,
            follow_cta_text=" ",
        )
