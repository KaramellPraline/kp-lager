"""Eigene Zertifizierungsstelle + Serverzertifikat für HTTPS im LAN (ohne Caddy).

Aufruf: uv run python tools/devcert.py [HOST ...] [--ip IP ...]
Ergebnis in data/certs/: ca.crt (aufs Handy installieren), ca.key, server.crt, server.key.
Die CA bleibt bestehen (Handys müssen sie nur einmal installieren); das Serverzertifikat
wird bei jedem Aufruf neu ausgestellt (397 Tage, iOS-kompatibel).
"""

import argparse
import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERTS = Path(__file__).parents[1] / "data" / "certs"


def _write_key(key: ec.EllipticCurvePrivateKey, path: Path) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def ensure_ca(folder: Path) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    crt, key = folder / "ca.crt", folder / "ca.key"
    if crt.exists() and key.exists():
        ca_key = serialization.load_pem_private_key(key.read_bytes(), None)
        assert isinstance(ca_key, ec.EllipticCurvePrivateKey)
        return x509.load_pem_x509_certificate(crt.read_bytes()), ca_key
    folder.mkdir(parents=True, exist_ok=True)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "KP Lager lokale CA")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )  # fmt: skip
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), False)
        .sign(ca_key, hashes.SHA256())
    )
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    _write_key(ca_key, key)
    return cert, ca_key


def issue_server(folder: Path, hosts: list[str], ips: list[str]) -> Path:
    ca, ca_key = ensure_ca(folder)
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.UTC)
    san = [x509.DNSName(h) for h in hosts] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=397))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False
        )
        .sign(ca_key, hashes.SHA256())
    )
    (folder / "server.crt").write_bytes(
        cert.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM)
    )
    _write_key(key, folder / "server.key")
    return folder / "server.crt"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("hosts", nargs="*", default=["lager.home.lan", "localhost"])
    ap.add_argument("--ip", action="append", default=[], help="zusätzliche IP-Adresse(n)")
    ap.add_argument("--dir", type=Path, default=CERTS)
    args = ap.parse_args()
    path = issue_server(args.dir, args.hosts, ["127.0.0.1", *args.ip])
    print(f"Serverzertifikat: {path}\nCA fürs Handy:    {args.dir / 'ca.crt'}")
