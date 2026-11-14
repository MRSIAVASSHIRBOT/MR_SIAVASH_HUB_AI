"""Compose an optional support CTA followed by an unconditional resource link."""
from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit


def validate_resource_url(resource_url: str) -> str:
    """Validate an absolute HTTPS resource URL without making network requests."""
    candidate = resource_url.strip()
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Resource URL must be an absolute HTTPS URL") from exc
    if (
        not candidate
        or any(character.isspace() for character in candidate)
        or parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Resource URL must be an absolute HTTPS URL")
    normalized_host = hostname.rstrip(".").lower()
    try:
        address = ip_address(normalized_host)
    except ValueError:
        address = None
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Resource URL port is invalid")
    if address is not None and not address.is_global:
        raise ValueError("Resource URL must not point to a private or local IP address")
    if address is None and (
        normalized_host == "localhost"
        or normalized_host.endswith((".localhost", ".local", ".internal"))
        or "." not in normalized_host
    ):
        raise ValueError("Resource URL must use a public hostname")
    return candidate


def build_optional_support_resource_reply(
    resource_url: str,
    *,
    resource_label: str = "محتوای آموزشی",
    intro_text: str = "سلام! ✨",
    include_follow: bool = True,
    follow_cta_text: str = (
        "اگر این آموزش برات مفیده، خوشحال می‌شیم صفحه‌مون رو دنبال کنی. 💚"
    ),
    include_share: bool = True,
    share_cta_text: str = (
        "این پست رو هم برای دوستانت بفرست تا افراد بیشتری از آموزش رایگان استفاده کنن. 📢"
    ),
) -> str:
    """Build a configurable reply; resource delivery never depends on engagement."""
    candidate = validate_resource_url(resource_url)
    label = resource_label.strip()
    intro = intro_text.strip()
    follow_text = follow_cta_text.strip()
    share_text = share_cta_text.strip()

    if not label or "\n" in label or "\r" in label:
        raise ValueError("Resource label must be a non-empty single line")
    for value, field_name in (
        (intro, "Intro text"),
        (follow_text, "Follow CTA"),
        (share_text, "Share CTA"),
    ):
        if len(value) > 500 or "\x00" in value:
            raise ValueError(f"{field_name} is invalid or too long")
    if include_follow and not follow_text:
        raise ValueError("Follow CTA text is required when Follow invitation is enabled")
    if include_share and not share_text:
        raise ValueError("Share CTA text is required when Share invitation is enabled")

    parts = []
    if intro:
        parts.append(intro)
    if include_follow:
        parts.append(follow_text)
    if include_share:
        parts.append(share_text)
    if include_follow or include_share:
        parts.append(
            "این حمایت کاملاً اختیاریه؛ برای دریافت محتوا نیازی به فالو یا "
            "اشتراک‌گذاری نیست."
        )
    # The educational link is always appended, including when both CTAs are disabled.
    parts.append(f"📚 لینک دریافت {label}:\n{candidate}")
    return "\n\n".join(parts)
