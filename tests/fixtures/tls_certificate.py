"""A self-signed certificate for one name or address, for a test starting a TLS server of its own.

The webhook sender and the mail relay are both held to what a receiver on the other end of a real
TLS connection reads, and both need a certificate a client can be told to trust and whose name can
be made to match or not. Written once here for both.

Task ids: none
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def certificate(directory: Path, name: str) -> tuple[Path, Path]:
    """A certificate for `name`, a host name or an IP address, and its key, written as PEM.

    Valid from 2020 to 3000, far outside any wall clock a test runs at, for the reason
    `tests/unit/test_scope_and_capability.py` gives about dates in fixtures.
    """
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    try:
        alternative: x509.GeneralName = x509.IPAddress(ipaddress.ip_address(name))
    except ValueError:
        alternative = x509.DNSName(name)
    made = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2020, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(3000, 1, 1, tzinfo=UTC))
        .add_extension(x509.SubjectAlternativeName([alternative]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    stem = name.replace(":", "_")
    cert = directory / f"{stem}.pem"
    private = directory / f"{stem}.key"
    cert.write_bytes(made.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert, private
