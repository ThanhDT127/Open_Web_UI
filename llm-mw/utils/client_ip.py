"""Resolve the address of the caller, not of the proxy in front of it.

Every request reaches this service through nginx, so the socket peer is always nginx and
the recorded address distinguishes nothing — the whole request log held 11 distinct
values, none of them a person.

The obvious fix, uvicorn's ``--proxy-headers``, is wrong here. It reads
``X-Forwarded-For``, and nginx builds that header with ``$proxy_add_x_forwarded_for``,
which *appends* the observed address to whatever the caller already put there. Its first
element is therefore the caller's own claim, and that is the element uvicorn takes.
Measured through nginx::

    curl -H "X-Forwarded-For: 203.0.113.55"   ->  recorded: 203.0.113.55

``X-Real-IP`` does not have this problem: nginx sets it with ``$remote_addr``, which
overwrites, so whatever the caller sent is discarded before the header leaves nginx. All
12 proxy blocks set it.

The header is honoured only when the connection itself came from inside the private
range, so a caller reaching this service directly cannot assert one. On production port
5000 is not published, so only containers can. On dev the override publishes it, which
means the developer's own machine can assert an address — accepted, it is their machine.
"""

import ipaddress
from typing import Optional

# RFC1918 plus loopback. Deliberately not the current compose subnet: Docker allocates
# those dynamically and this project has already drifted 172.19 -> 172.18 -> 172.19.
# Pinning one would fail silently — the header would stop being honoured and the address
# would quietly revert to the proxy's, which is the defect this module exists to fix.
_TRUSTED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]


def _is_trusted(host: Optional[str]) -> bool:
    if not host:
        return False
    try:
        return any(ipaddress.ip_address(host) in net for net in _TRUSTED_NETS)
    except ValueError:
        return False


def client_address(request) -> Optional[str]:
    """The caller's address: X-Real-IP when it comes via the trusted proxy, else the peer.

    Returns ``None`` when neither is available, matching the previous behaviour of
    ``getattr(request.client, "host", None)``.
    """
    peer = getattr(getattr(request, "client", None), "host", None)
    if _is_trusted(peer):
        real = request.headers.get("x-real-ip")
        if real:
            real = real.strip()
            # Only accept something that parses as an address; a header that reached us
            # malformed is not evidence about anything.
            try:
                ipaddress.ip_address(real)
                return real
            except ValueError:
                pass
    return peer
