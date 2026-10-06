import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit


def public_address(address) -> bool:
    address = ipaddress.ip_address(address)
    if not address.is_global or address.is_multicast or address.is_reserved or address.is_unspecified:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        # Avoid translation/tunnelling destinations that can encode forbidden IPv4 addresses.
        if address.ipv4_mapped or address.sixtofour or address.teredo:
            return False
        if address in ipaddress.ip_network("64:ff9b::/96") or address in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    return True


def test_fixture_url(url: str) -> bool:
    from .config import settings

    parsed = urlsplit(url)
    return (
        (
            (settings.test_fixture_http and settings.mode == "fixture")
            or (
                settings.live_validation_fixture
                and settings.mode == "live"
                and parsed.path == "/overflow"
                and not parsed.query
            )
        )
        and parsed.scheme == "http"
        and parsed.hostname == "fixture.siteproof.test"
        and parsed.port in (None, 80)
        and parsed.username is None
        and parsed.password is None
    )


def validate_url(url: str, resolve=True) -> str:
    try:
        if any(ord(char) <= 32 or ord(char) == 127 for char in url):
            raise ValueError("Whitespace or control characters in URLs are forbidden")
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("Only credential-free HTTP/HTTPS URLs are supported")
        if parsed.port not in (None, 80 if parsed.scheme == "http" else 443):
            raise ValueError("Only ports 80 and 443 are allowed")
        host = parsed.hostname.rstrip(".").lower()
        if host in ("localhost", "metadata.google.internal") or host.endswith(".localhost"):
            raise ValueError("Private destinations are forbidden")
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            addresses = []
            if resolve and not test_fixture_url(url):
                addresses = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, parsed.port or 443)]
        if (resolve and not addresses and not test_fixture_url(url)) or any(not public_address(address) for address in addresses):
            raise ValueError("Non-public destination is forbidden")
        return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Unsafe or unresolved URL: {exc}") from exc


def valid_phone(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"\+?[0-9(). \-]+", value)) and 7 <= len(re.sub(r"\D", "", value)) <= 15
