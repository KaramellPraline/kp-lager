"""Etikettendruck über MQTT: der Server (z. B. auf dem Pi) schickt Aufträge an den Druck-Agenten
auf dem PC mit dem D30 (`app/print_agent.py`). Auch andere Programme können so drucken.

Themen (Schema in docs/PRINT_MQTT.md):
  print/d30/queue   Auftrag (JSON) -> Agent        {"id", "app", "images": [PNG base64]}
                                                    oder {"labels": [{"text", "extra", "qr"}]}
  print/d30/result  Ergebnis des Agenten           {"id", "ok", "printed", "error"}
  print/d30/status  Agent online/offline (retained) {"online", "available", "msg"}

Einstellung: Einstellungen › Anbindungen › Druck (Datenbank) oder per Umgebung
LAGER_PRINT_MQTT=host[:port], LAGER_PRINT_MQTT_USER, LAGER_PRINT_MQTT_PASSWORD
(oder LAGER_PRINT_MQTT_PASSWORD_FILE), LAGER_PRINT_MQTT_TOPIC. Die Umgebung hat Vorrang.
Das Passwort liegt in der Datenbank als `secret:mqtt_password` (nie im JSON-Export, nie im Log).
"""

import base64
import io
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app import codes, labelimg, labels, mqttmini
from app.repo import LagerError

BASE = "print/d30"
T_QUEUE, T_RESULT, T_STATUS = f"{BASE}/queue", f"{BASE}/result", f"{BASE}/status"
MAX_IMAGES = 30
MAX_IMAGE_BYTES = 200_000
DB_PATH: Path | None = None  # vom Server gesetzt (create_app): Einstellungen aus der Datenbank


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    user: str
    password: str
    topic: str  # Basis der Themen, Standard print/d30
    source: str  # "env" (Umgebung) oder "db" (Einstellungen › Anbindungen)

    def t(self, name: str) -> str:
        return f"{self.topic}/{name}"


def _env_password() -> str:
    if file := os.environ.get("LAGER_PRINT_MQTT_PASSWORD_FILE", ""):
        return Path(file).read_text(encoding="utf-8-sig").strip()
    return os.environ.get("LAGER_PRINT_MQTT_PASSWORD", "")


def _port(raw: str) -> int:
    try:
        return max(1, min(65535, int(raw)))
    except ValueError:
        return 1883


def env_set() -> bool:
    return bool(os.environ.get("LAGER_PRINT_MQTT", "").strip())


def from_db(conn: sqlite3.Connection) -> Config | None:
    host = codes.get_setting(conn, "mqtt_host", "").strip()
    if not host:
        return None
    return Config(
        host, _port(codes.get_setting(conn, "mqtt_port", "1883")),
        codes.get_setting(conn, "mqtt_user", ""), codes.get_secret(conn, "mqtt_password"),
        codes.get_setting(conn, "mqtt_topic", "").strip().strip("/") or BASE, "db",
    )  # fmt: skip


def config(conn: sqlite3.Connection | None = None) -> Config | None:
    """Wirksame Einstellung: Umgebung vor Datenbank; None = MQTT-Druck nicht eingerichtet."""
    if env_set():
        host, _, port = os.environ["LAGER_PRINT_MQTT"].strip().partition(":")
        topic = os.environ.get("LAGER_PRINT_MQTT_TOPIC", "").strip().strip("/") or BASE
        return Config(
            host, _port(port or "1883"), os.environ.get("LAGER_PRINT_MQTT_USER", ""),
            _env_password(), topic, "env",
        )  # fmt: skip
    if conn is not None:
        return from_db(conn)
    if DB_PATH is None or not DB_PATH.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            return from_db(db)
        finally:
            db.close()
    except sqlite3.Error:
        return None


def configured() -> bool:
    return config() is not None


def client(suffix: str = "", cfg: Config | None = None) -> mqttmini.Client:
    cfg = cfg or config()
    if cfg is None:
        raise LagerError("MQTT-Druck ist nicht eingerichtet")
    return mqttmini.Client(
        cfg.host, cfg.port, cfg.user, cfg.password,
        client_id=f"kp-lager-{suffix or uuid.uuid4().hex[:6]}",
    )  # fmt: skip


def encode_images(images: list[Image.Image]) -> list[str]:
    out = []
    for img in images:
        buf = io.BytesIO()
        img.convert("1").save(buf, "PNG", optimize=True)
        out.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    return out


def decode_job(job: dict[str, Any]) -> list[Image.Image]:
    """Bilder (320×96, 1 bit) aus einem Auftrag; prüft Anzahl und Größe."""
    images: list[Image.Image] = []
    for raw in job.get("images", []):
        data = base64.b64decode(str(raw), validate=True)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Bild zu groß")
        img = Image.open(io.BytesIO(data)).convert("L")
        if img.size != (labelimg.W, labelimg.H):
            img = img.resize((labelimg.W, labelimg.H))
        images.append(img.convert("1"))
    for spec in job.get("labels", []):
        text = str(spec.get("text", ""))[:80]
        qr = str(spec.get("qr", "") or text)
        label = labels.Label(str(spec.get("code", "")), qr, text, str(spec.get("extra", ""))[:80])
        images.append(labelimg.render(label))
    if not images:
        raise ValueError("Auftrag ohne Etiketten")
    if len(images) > MAX_IMAGES:
        raise ValueError(f"Höchstens {MAX_IMAGES} Etiketten je Auftrag")
    return images


def agent_state(timeout: float = 3.0, cfg: Config | None = None) -> tuple[bool, bool, str]:
    """(Agent online, Drucker erreichbar, Hinweis) – liest die gehaltene Statusnachricht."""
    cfg = cfg or config()
    if cfg is None:
        return False, False, "MQTT-Druck ist nicht eingerichtet"
    c = client("status", cfg)
    try:
        c.connect(timeout)
        c.subscribe(cfg.t("status"))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if msg := c.poll(0.5):
                data = json.loads(msg[1] or b"{}")
                if not data.get("online"):
                    return False, False, "Druck-Agent ist offline (PC aus?)"
                return True, bool(data.get("available")), str(data.get("msg", ""))
    except (OSError, mqttmini.MqttError, ValueError) as exc:
        return False, False, f"MQTT: {exc}"[:120]
    finally:
        c.close()
    return False, False, "Kein Druck-Agent gemeldet"


def agent_status(timeout: float = 3.0) -> tuple[bool, str]:
    """(Drucker über den Agenten erreichbar, Hinweis) fürs Status-Symbol."""
    _online, available, msg = agent_state(timeout)
    return available, msg


def submit(images: list[Image.Image], app: str = "kp-lager") -> int:
    """Auftrag an den Agenten schicken und auf sein Ergebnis warten. Fehler -> LagerError."""
    if not 0 < len(images) <= MAX_IMAGES:
        raise LagerError(f"1 bis {MAX_IMAGES} Etiketten je Auftrag")
    cfg = config()
    if cfg is None:
        raise LagerError("MQTT-Druck ist nicht eingerichtet")
    online, _available, msg = agent_state(cfg=cfg)
    if not online:  # Drucker gerade aus: trotzdem senden, der Agent versucht es selbst
        raise LagerError(msg or "Druck-Agent nicht erreichbar")
    job_id = uuid.uuid4().hex[:12]
    c = client(job_id, cfg)
    try:
        c.connect()
        c.subscribe(cfg.t("result"))
        body = json.dumps({"id": job_id, "app": app, "images": encode_images(images)})
        c.publish(cfg.t("queue"), body)
        end = time.monotonic() + 25 + 4 * len(images)
        while time.monotonic() < end:
            if msg_ := c.poll(1.0):
                data = json.loads(msg_[1] or b"{}")
                if data.get("id") != job_id:
                    continue
                if not data.get("ok"):
                    raise LagerError(f"Druck fehlgeschlagen: {data.get('error', '?')}"[:160])
                return int(data.get("printed", len(images)))
    except (OSError, mqttmini.MqttError, ValueError) as exc:
        raise LagerError(f"Druck-Agent nicht erreichbar: {exc}"[:160]) from exc
    finally:
        c.close()
    raise LagerError("Druck-Agent hat nicht geantwortet – ist der PC mit dem D30 an?")


def test_connection(cfg: Config, timeout: float = 4.0) -> tuple[bool, str]:
    """Knopf „Testen“: Verbindung zum Broker aufbauen und Agent-Status lesen."""
    c = client("test", cfg)
    try:
        c.connect(timeout)
    except (OSError, mqttmini.MqttError, ValueError) as exc:
        return False, f"Broker nicht erreichbar: {exc}"[:160]
    finally:
        c.close()
    online, available, msg = agent_state(timeout, cfg)
    if not online:
        return True, f"Broker erreichbar, {msg or 'kein Druck-Agent gemeldet'}"
    return True, "Broker und Druck-Agent erreichbar" + ("" if available else f" – D30: {msg}")
