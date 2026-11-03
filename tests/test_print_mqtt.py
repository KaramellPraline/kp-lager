"""Etikettendruck über MQTT: Client, Auftrag, Agent – gegen einen kleinen Broker im Test."""

import argparse
import json
import socket
import struct
import threading
from pathlib import Path

import pytest
from PIL import Image

from app import labelimg, mqttmini, print_agent, printmq
from app.repo import LagerError


class FakeBroker:
    """Nimmt Verbindungen an, merkt Abos je Verbindung, verteilt Veröffentlichungen (QoS 0)."""

    def __init__(self) -> None:
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(8)
        self.port = self.srv.getsockname()[1]
        self.subs: list[tuple[socket.socket, str]] = []
        self.retained: dict[str, bytes] = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    @staticmethod
    def _read(conn: socket.socket) -> tuple[int, bytes]:
        def exact(n: int) -> bytes:
            buf = b""
            while len(buf) < n:
                chunk = conn.recv(n - len(buf))
                if not chunk:
                    raise OSError
                buf += chunk
            return buf

        first = exact(1)[0]
        size, mult = 0, 1
        while True:
            b = exact(1)[0]
            size += (b & 0x7F) * mult
            if not b & 0x80:
                break
            mult *= 128
        return first, exact(size) if size else b""

    def _serve(self, conn: socket.socket) -> None:
        try:
            while True:
                first, body = self._read(conn)
                kind = first >> 4
                if kind == 1:  # CONNECT
                    conn.sendall(b"\x20\x02\x00\x00")
                elif kind == 8:  # SUBSCRIBE
                    (tlen,) = struct.unpack("!H", body[2:4])
                    topic = body[4 : 4 + tlen].decode()
                    with self.lock:
                        self.subs.append((conn, topic))
                        kept = self.retained.get(topic)
                    conn.sendall(b"\x90\x03" + body[:2] + b"\x00")
                    if kept is not None:
                        conn.sendall(mqttmini.publish_packet(topic, kept, True))
                elif kind == 3:  # PUBLISH
                    (tlen,) = struct.unpack("!H", body[:2])
                    topic = body[2 : 2 + tlen].decode()
                    payload = body[2 + tlen :]
                    with self.lock:
                        if first & 1:
                            self.retained[topic] = payload
                        targets = [c for c, t in self.subs if t == topic]
                    for c in targets:
                        c.sendall(mqttmini.publish_packet(topic, payload))
                elif kind == 12:  # PINGREQ
                    conn.sendall(b"\xd0\x00")
                elif kind == 14:
                    return
        except OSError:
            pass
        finally:
            with self.lock:
                self.subs = [(c, t) for c, t in self.subs if c is not conn]
            conn.close()


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> FakeBroker:
    b = FakeBroker()
    monkeypatch.setenv("LAGER_PRINT_MQTT", f"127.0.0.1:{b.port}")
    monkeypatch.setenv("LAGER_PRINT_MQTT_USER", "kp-lager")
    monkeypatch.setenv("LAGER_PRINT_MQTT_PASSWORD", "geheim")
    return b


def _label_image() -> Image.Image:
    from app import labels

    return labelimg.render(labels.Label("ART-0001", "https://lager.home.lan/c/ART-0001", "M3x10"))


def test_packets_roundtrip_and_remaining_length() -> None:
    assert mqttmini._length(0) == b"\x00" and mqttmini._length(321) == b"\xc1\x02"
    pkt = mqttmini.publish_packet("a/b", b"x" * 200)
    assert pkt[0] == 0x30 and pkt[1:3] == b"\xcd\x01"  # 205 Bytes Restlänge, zwei Längenbytes
    conn = mqttmini.connect_packet("id", "u", "p", 60, mqttmini.Will("t", b"off"))
    assert conn[0] == 0x10 and b"MQTT" in conn and conn.endswith(b"\x00\x01u\x00\x01p")


def test_decode_job_images_and_labels_and_limits() -> None:
    img = _label_image()
    jobs = printmq.decode_job({"images": printmq.encode_images([img, img])})
    assert len(jobs) == 2 and jobs[0].size == (320, 96) and jobs[0].mode == "1"
    made = printmq.decode_job({"labels": [{"text": "Netzteil 12V", "extra": "Regal 2", "qr": "x"}]})
    assert len(made) == 1 and made[0].size == (320, 96)
    with pytest.raises(ValueError):
        printmq.decode_job({})
    with pytest.raises(ValueError):
        printmq.decode_job({"images": printmq.encode_images([img] * 31)})
    with pytest.raises(ValueError):
        printmq.decode_job({"images": ["das-ist-kein-base64!"]})


def test_handle_job_reports_success_and_errors() -> None:
    got: list[int] = []
    job = json.dumps({"id": "j1", "images": printmq.encode_images([_label_image()])}).encode()
    assert print_agent.handle_job(job, lambda imgs: got.append(len(imgs))) == {
        "id": "j1", "ok": True, "printed": 1}  # fmt: skip
    assert got == [1]

    def broken(_imgs: list[Image.Image]) -> None:
        raise LagerError("D30 nicht gefunden")

    bad = print_agent.handle_job(job, broken)
    assert bad["ok"] is False and "D30" in bad["error"] and bad["id"] == "j1"
    assert print_agent.handle_job(b"kaputt", broken)["ok"] is False


def _start_agent(broker: FakeBroker, tmp_path: Path) -> None:
    pw = tmp_path / "pw.txt"
    pw.write_text("geheim", encoding="utf-8")
    args = argparse.Namespace(broker="127.0.0.1", port=broker.port, user="kp-desktop-print",
                              password_file=str(pw), dry_run=True)  # fmt: skip
    threading.Thread(target=print_agent.run, args=(args,), daemon=True).start()


def test_submit_round_trip_with_agent(broker: FakeBroker, tmp_path: Path) -> None:
    _start_agent(broker, tmp_path)
    for _ in range(50):  # warten, bis der Agent seinen Status veröffentlicht hat
        if broker.retained.get(printmq.T_STATUS):
            break
        threading.Event().wait(0.1)
    online, available, msg = printmq.agent_state()
    assert online and available and "Probelauf" in msg
    assert printmq.submit([_label_image(), _label_image()]) == 2


def test_submit_without_agent_fails_clearly(broker: FakeBroker) -> None:
    with pytest.raises(LagerError, match="Kein Druck-Agent"):
        printmq.submit([_label_image()])
    ok, msg = printmq.agent_status()
    assert not ok and "Kein Druck-Agent" in msg


def test_wrong_credentials_are_reported() -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def deny() -> None:
        conn, _ = srv.accept()
        conn.recv(200)
        conn.sendall(b"\x20\x02\x00\x04")
        conn.close()

    threading.Thread(target=deny, daemon=True).start()
    c = mqttmini.Client("127.0.0.1", srv.getsockname()[1], "x", "y")
    with pytest.raises(mqttmini.MqttError, match="Passwort"):
        c.connect()
    srv.close()
