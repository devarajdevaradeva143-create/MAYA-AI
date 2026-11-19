"""TLS certificate management skeleton for WAN remote control.

Design: `docs/WAN-REMOTE-DESIGN.md`.

Two modes:
- ``lan``: self-signed CA + per-device certs (no external PKI).
- ``wan``: ACME/Let's Encrypt (or a user-provided certificate chain).

Only the interface + self-signed path are implemented here; the ACME path
raises ``NotImplementedError`` with a clear message.
"""

from __future__ import annotations

import datetime
import ipaddress
from pathlib import Path
from typing import Any


def create_ssl_context(
    *,
    mode: str = "lan",
    cert_path: str = "",
    key_path: str = "",
    ca_path: str = "",
) -> Any:
    """Return an ``ssl.SSLContext`` for the chosen mode.

    ``mode='lan'`` builds a self-signed context from ``cert_path``/``key_path``.
    ``mode='wan'`` requires valid certificates and is not implemented yet.
    """
    import ssl

    if mode == "wan":
        raise NotImplementedError(
            "WAN TLS needs ACME/Let's Encrypt; supply cert_path/key_path and mode='lan' "
            "until the relay design is deployed."
        )
    if mode != "lan":
        raise ValueError(f"unknown TLS mode: {mode}")

    if not cert_path or not key_path:
        raise ValueError("lan mode requires cert_path and key_path")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    if ca_path:
        context.load_verify_locations(ca_path)
    return context


def ensure_self_signed(
    cert_dir: str,
    *,
    hostname: str = "maya.local",
    valid_days: int = 365,
) -> dict[str, Any]:
    """Create a self-signed certificate for ``hostname`` if missing.

    Uses ``cryptography`` when available; otherwise returns a clear error.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("cryptography is required for self-signed certificates") from exc

    directory = Path(cert_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    cert_path = directory / "maya.crt"
    key_path = directory / "maya.key"

    if cert_path.exists() and key_path.exists():
        return {"ok": True, "cert": str(cert_path), "key": str(key_path), "created": False}

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, hostname)]
    )
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None
    san = (
        x509.SubjectAlternativeName([x509.IPAddress(ip)])
        if ip is not None
        else x509.SubjectAlternativeName([x509.DNSName(hostname)])
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=int(valid_days)))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return {"ok": True, "cert": str(cert_path), "key": str(key_path), "created": True}


__all__ = ["create_ssl_context", "ensure_self_signed"]
