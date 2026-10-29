"""Suite-wide safeguards that keep tests isolated from external providers."""

import ipaddress
import socket

import pytest


class ExternalNetworkBlocked(OSError):
    """Raised when a test tries to open a non-loopback socket."""


def _is_loopback(address, family):
    if family == getattr(socket, "AF_UNIX", None):
        return True
    if not isinstance(address, tuple) or not address:
        return False

    host = address[0]
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="ignore")
    if not isinstance(host, str):
        return False
    if host.rstrip(".").lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


@pytest.fixture(autouse=True)
def no_external_provider_access(monkeypatch):
    """Remove provider credentials and reject every non-loopback connection."""
    for name in ("NEBIUS_API_KEY", "NVIDIA_API_KEY", "NVIDIA_DEV_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(sock, address):
        if not _is_loopback(address, sock.family):
            raise ExternalNetworkBlocked(f"external network access blocked: {address!r}")
        return real_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if not _is_loopback(address, sock.family):
            raise ExternalNetworkBlocked(f"external network access blocked: {address!r}")
        return real_connect_ex(sock, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
