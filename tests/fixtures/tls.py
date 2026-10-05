"""A certificate authority and a server certificate made for one test run, and never committed.

The Laravel executor verifies the database server's certificate by name and chain
(`brain.connectors.laravel.A_LOGIN_CROSSES_ONLY_A_VERIFIED_CHANNEL`), so proving it needs a
server whose certificate a test controls. This makes one at run time: an authority, and a server
certificate it signed for `127.0.0.1` and `localhost`, with the extensions the standard library's
strict verification asks for. The unit tests hand them to a local TLS socket; the CI job
`laravel_mysql` writes them to files and starts MySQL with them:

    uv run python -m tests.fixtures.tls <directory>

Generated rather than committed, because a private key in the repository is a private key in its
history, whatever it was for.

Task ids: M11.6.1
"""

from __future__ import annotations

import ipaddress
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@dataclass(frozen=True)
class Issued:
    """An authority's certificate, and a server certificate and key it signed, all as PEM."""

    authority: str
    certificate: str
    key: str


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def issued(names: tuple[str, ...] = ("127.0.0.1", "localhost")) -> Issued:
    """A fresh authority and a server certificate for `names`, valid from a day ago for a week."""
    now = datetime.now(UTC)
    authority_key, server_key = _key(), _key()
    authority_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test authority")])
    authority = (
        x509.CertificateBuilder()
        .subject_name(authority_name)
        .issuer_name(authority_name)
        .public_key(authority_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(authority_key.public_key()), critical=False
        )
        .sign(authority_key, hashes.SHA256())
    )
    alternatives: list[x509.GeneralName] = []
    for name in names:
        try:
            alternatives.append(x509.IPAddress(ipaddress.ip_address(name)))
        except ValueError:
            alternatives.append(x509.DNSName(name))
    server = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
        .issuer_name(authority_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName(alternatives), critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()),
            critical=False,
        )
        .sign(authority_key, hashes.SHA256())
    )
    return Issued(
        authority=authority.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        certificate=server.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        key=server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode("ascii"),
    )


def write(directory: Path) -> Issued:
    """Write `ca.pem`, `server.pem` and `server-key.pem`, readable by a container's server."""
    directory.mkdir(parents=True, exist_ok=True)
    made = issued()
    for name, text in (
        ("ca.pem", made.authority),
        ("server.pem", made.certificate),
        ("server-key.pem", made.key),
    ):
        path = directory / name
        path.write_text(text, encoding="ascii", newline="\n")
        # Read by the database server's own user inside its container, and thrown away with the
        # runner: a key made for one job, protecting nothing but that job's test data.
        path.chmod(0o644)
    return made


if __name__ == "__main__":
    write(Path(sys.argv[1]))
