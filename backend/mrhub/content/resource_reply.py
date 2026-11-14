"""Compose an optional support CTA followed by an unconditional resource link.

This helper deliberately has no follower/share-state inputs: access to the resource
must never depend on either interaction.
"""
from __future__ import annotations

from urllib.parse import urlsplit


def build_optional_support_resource_reply(
    resource_url: str,
    *,
    resource_label: str = "محتوای آموزشی",
) -> str:
    """Return a Persian reply that invites support, then always includes the resource.

    Only absolute HTTPS URLs with a hostname and valid optional port are accepted.
    Public reachability is an external activation check, not inferred by this helper.
    No follow/share verification or gating is performed here.
    """
    candidate = resource_url.strip()
    parsed = urlsplit(candidate)
    try:
        hostname = parsed.hostname
        parsed.port  # Validate port syntax and range.
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

    label = resource_label.strip()
    if not label or "\n" in label or "\r" in label:
        raise ValueError("Resource label must be a non-empty single line")

    return (
        "سلام! ✨\n\n"
        "اگر این آموزش برات مفیده، خوشحال می‌شیم صفحه‌مون رو دنبال کنی و "
        "این پست رو برای دوستانت هم بفرستی. 💚\n\n"
        "این حمایت کاملاً اختیاریه؛ برای دریافت محتوا نیازی به فالو یا "
        "اشتراک‌گذاری نیست.\n\n"
        f"📚 لینک دریافت {label}:\n"
        f"{candidate}"
    )
