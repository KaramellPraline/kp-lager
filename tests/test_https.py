import sys
from pathlib import Path

from cryptography import x509
from fastapi.testclient import TestClient

from app.config import Settings
from app.web import create_app

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import devcert  # noqa: E402


def test_devcert_issues_server_cert_signed_by_ca(tmp_path: Path) -> None:
    devcert.issue_server(tmp_path, ["lager.home.lan", "localhost"], ["127.0.0.1", "192.168.74.5"])
    ca = x509.load_pem_x509_certificate((tmp_path / "ca.crt").read_bytes())
    leaf = x509.load_pem_x509_certificates((tmp_path / "server.crt").read_bytes())[0]
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.DNSName) == ["lager.home.lan", "localhost"]
    assert [str(i) for i in san.get_values_for_type(x509.IPAddress)] == [
        "127.0.0.1",
        "192.168.74.5",
    ]
    leaf.verify_directly_issued_by(ca)
    # CA bleibt beim zweiten Aufruf gleich (Handys installieren sie nur einmal)
    devcert.issue_server(tmp_path, ["lager.home.lan"], [])
    assert (tmp_path / "ca.crt").read_bytes() == ca.public_bytes(devcert.serialization.Encoding.PEM)


def test_ca_download_and_https_redirect(tmp_path: Path) -> None:
    devcert.issue_server(tmp_path / "certs", ["lager.home.lan"], [])
    plain = Settings(data_dir=tmp_path, base_url="https://lager.home.lan")
    with TestClient(create_app(plain)) as c:
        r = c.get("/ca.crt")
        assert r.headers["content-type"] == "application/x-x509-ca-cert"
        assert r.content.startswith(b"-----BEGIN CERTIFICATE-----")
        assert c.get("/").status_code == 200
    redirecting = Settings(
        data_dir=tmp_path, base_url="https://lager.home.lan", https_redirect=True
    )
    with TestClient(create_app(redirecting), base_url="http://lager.home.lan") as c:
        r = c.get("/C/EUR-001", follow_redirects=False)
        assert r.status_code == 308 and r.headers["location"] == "https://lager.home.lan/C/EUR-001"
        assert c.get("/ca.crt", follow_redirects=False).status_code == 200


def test_ca_missing_gives_404(client: TestClient) -> None:
    assert client.get("/ca.crt").status_code == 404
