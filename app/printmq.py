"""Etikettendruck über MQTT: der Server (z. B. auf dem Pi) schickt Aufträge an den Druck-Agenten
auf dem PC mit dem D30 (`app/print_agent.py`). Auch andere Programme können so drucken.

Themen (Schema in docs/PRINT_MQTT.md):
  print/d30/queue   Auftrag (JSON) -> Agent        {"id", "app", "images": [PNG base64]}
                                                    oder {"labels": [{"text", "extra", "qr"}]}
  print/d30/result  Ergebnis des Agenten           {"id", "ok", "printed", "error"}
  print/d30/status  Agent online/offline (retained) {"online", "available", "msg"}

Einstellung: LAGER_PRINT_MQTT=host[:port], LAGER_PRINT_MQTT_USER, LAGER_PRINT_MQTT_PASSWORD
(oder LAGER_PRINT_MQTT_PASSWORD_FILE).
"""

import base64
import io
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from app import labelimg, labels, mqttmini
from app.repo import LagerError

T_QUEUE, T_RESULT, T_STATUS = "print/d30/queue", "print/d30/result", "print/d30/status"
MAX_IMAGES = 30
MAX_IMAGE_BYTES = 200_000


def configured() -> bool:
    return bool(os.environ.get("LAGER_PRINT_MQTT", "").strip())


def _password() -> str:
    if file := os.environ.get("LAGER_PRINT_MQTT_PASSWORD_FILE", ""):
        return Path(file).read_text(encoding="utf-8-sig").strip()
    return os.environ.get("LAGER_PRINT_MQTT_PASSWORD", "")


def client(suffix: str = "") -> mqttmini.Client:
    host, _, port = os.environ["LAGER_PRINT_MQTT"].strip().partition(":")
    return mqttmini.Client(
        host, int(port or 1883), os.environ.get("LAGER_PRINT_MQTT_USER", ""), _password(),
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


def agent_state(timeout: float = 3.0) -> tuple[bool, bool, str]:
    """(Agent online, Drucker erreichbar, Hinweis) – liest die gehaltene Statusnachricht."""
    c = client("status")
    try:
        c.connect(timeout)
        c.subscribe(T_STATUS)
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
    online, _available, msg = agent_state()
    if not online:  # Drucker gerade aus: trotzdem senden, der Agent versucht es selbst
        raise LagerError(msg or "Druck-Agent nicht erreichbar")
    job_id = uuid.uuid4().hex[:12]
    c = client(job_id)
    try:
        c.connect()
        c.subscribe(T_RESULT)
        body = json.dumps({"id": job_id, "app": app, "images": encode_images(images)})
        c.publish(T_QUEUE, body)
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
