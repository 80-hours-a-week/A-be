"""Cross-Unit external-query hygiene primitives (U11 web-references extension §2).

Why here: ``sanitize_external_query`` / ``is_safe_external_url`` were pure functions inside
U12 (``novelty.security``), but U11 (evidence) now needs them for the scholarly web-reference
adapter — an evidence→novelty import would invert the Unit dependency direction. Like the
#167 authz move, they are pure data transforms with no I/O and no module state, so they hoist
cleanly into the shared contract layer. ``novelty.security`` re-exports these names verbatim
(identity preserved), so existing U12 consumers and tests keep working unchanged.

BR-WR3/BR-WR4 rely on these: outbound queries are whitespace-collapsed and capped (≤180 chars
by default), and only provider-returned https URLs on an allowlisted host survive.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

__all__ = [
    "ALLOWED_EXTERNAL_HOSTS",
    "is_safe_external_url",
    "sanitize_external_query",
]

# Default allowlist — the external hosts U12 novelty talks to. Callers with a narrower
# surface (e.g. the U11 scholarly adapter) pass their own ``allowed_hosts`` explicitly.
ALLOWED_EXTERNAL_HOSTS = frozenset(
    {
        "github.com",
        "api.github.com",
        "huggingface.co",
        "kaggle.com",
        "www.kaggle.com",
        "paperswithcode.com",
        "zenodo.org",
        "notion.com",
        "api.notion.com",
    }
)


def sanitize_external_query(text: str, *, max_len: int = 180) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:max_len]


def is_safe_external_url(url: str, allowed_hosts: set[str] | frozenset[str] | None = None) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return False
    hosts = allowed_hosts or ALLOWED_EXTERNAL_HOSTS
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in hosts)
