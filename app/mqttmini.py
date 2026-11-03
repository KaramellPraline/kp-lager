"""Minimaler MQTT-3.1.1-Client (nur Standardbibliothek): verbinden, abonnieren, veröffentlichen.

Reicht für den Etikettendruck über den Hausbroker (QoS 0, kein TLS, ein Thread).
"""

import contextlib
import socket
import struct
import time
from dataclasses import dataclass


class MqttError(Exception):
    pass


@dataclass(frozen=True)
class Will:
    topic: str
    payload: bytes
    retain: bool = True


def _str(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("!H", len(raw)) + raw


def _length(n: int) -> bytes:
    out = bytearray()
    while True:
        byte, n = n % 128, n // 128
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def packet(first: int, body: bytes) -> bytes:
    return bytes([first]) + _length(len(body)) + body


def connect_packet(
    client_id: str, user: str, password: str, keepalive: int, will: Will | None
) -> bytes:
    flags = 0x02  # clean session
    payload = _str(client_id)
    if will is not None:
        flags |= 0x04 | (0x20 if will.retain else 0)
        payload += _str(will.topic) + struct.pack("!H", len(will.payload)) + will.payload
    if user:
        flags |= 0x80 | 0x40
        payload += _str(user) + _str(password)
    body = _str("MQTT") + bytes([4, flags]) + struct.pack("!H", keepalive) + payload
    return packet(0x10, body)


def publish_packet(topic: str, payload: bytes, retain: bool = False) -> bytes:
    return packet(0x30 | (1 if retain else 0), _str(topic) + payload)


def subscribe_packet(topic: str, packet_id: int = 1) -> bytes:
    return packet(0x82, struct.pack("!H", packet_id) + _str(topic) + b"\x00")


class Client:
    def __init__(
        self,
        host: str,
        port: int = 1883,
        user: str = "",
        password: str = "",
        client_id: str = "kp-client",
        keepalive: int = 60,
        will: Will | None = None,
    ) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password
        self.client_id, self.keepalive, self.will = client_id, keepalive, will
        self.sock: socket.socket | None = None
        self._last_sent = 0.0

    # --- Verbindung ------------------------------------------------------------------------

    def connect(self, timeout: float = 8.0) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self._send(connect_packet(self.client_id, self.user, self.password, self.keepalive,
                                  self.will))  # fmt: skip
        first, body = self._read(timeout)
        if first != 0x20 or len(body) < 2:
            raise MqttError("Broker antwortet nicht wie erwartet")
        if body[1] != 0:
            reasons = {4: "Benutzer/Passwort falsch", 5: "nicht erlaubt"}
            raise MqttError(f"Broker lehnt ab: {reasons.get(body[1], body[1])}")

    def close(self) -> None:
        if self.sock is not None:
            with contextlib.suppress(OSError):
                self._send(b"\xe0\x00")
            self.sock.close()
            self.sock = None

    def _send(self, data: bytes) -> None:
        if self.sock is None:
            raise MqttError("nicht verbunden")
        self.sock.sendall(data)
        self._last_sent = time.monotonic()

    def _exact(self, n: int) -> bytes:
        assert self.sock is not None
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise MqttError("Verbindung vom Broker getrennt")
            buf += chunk
        return buf

    def _read(self, timeout: float) -> tuple[int, bytes]:
        assert self.sock is not None
        self.sock.settimeout(timeout)
        first = self._exact(1)[0]
        self.sock.settimeout(10.0)  # Rest des Pakets kommt sofort
        size, mult = 0, 1
        while True:
            byte = self._exact(1)[0]
            size += (byte & 0x7F) * mult
            if not byte & 0x80:
                break
            mult *= 128
        return first, self._exact(size) if size else b""

    # --- Nachrichten -----------------------------------------------------------------------

    def publish(self, topic: str, payload: bytes | str, retain: bool = False) -> None:
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        self._send(publish_packet(topic, data, retain))

    def subscribe(self, topic: str) -> None:
        self._send(subscribe_packet(topic))

    def poll(self, timeout: float = 1.0) -> tuple[str, bytes] | None:
        """Nächste Nachricht (Thema, Inhalt) oder None nach `timeout` s; hält die Verbindung."""
        if self.sock is not None and time.monotonic() - self._last_sent > self.keepalive / 2:
            self._send(b"\xc0\x00")
        try:
            first, body = self._read(timeout)
        except TimeoutError:
            return None
        if first >> 4 != 3 or len(body) < 2:  # SUBACK, PINGRESP usw. ignorieren
            return None
        (tlen,) = struct.unpack("!H", body[:2])
        topic = body[2 : 2 + tlen].decode("utf-8", "replace")
        skip = 2 + tlen + (2 if (first >> 1) & 3 else 0)  # Paket-ID nur bei QoS > 0
        return topic, body[skip:]
