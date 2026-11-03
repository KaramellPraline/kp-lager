"""Druck-Agent für den PC mit dem D30: nimmt Aufträge vom MQTT-Broker an und druckt sie.

Läuft neben dem Desktop-Agenten (kp-desktop) auf dem PC, der den D30 per Bluetooth erreicht.
Der Lager-Server (Pi) und jedes andere Programm legt Aufträge in `print/d30/queue` ab
(Schema: docs/PRINT_MQTT.md, Gegenstück zum Senden: app/printmq.py).

Start:  python -m app.print_agent --broker 192.168.74.6 --password-file <Datei>
        (Datei: kp-server_mqtt_kp-desktop-print_password.txt, siehe docs/PRINT_MQTT.md)
Probelauf ohne Drucker: --dry-run (druckt nicht, meldet aber Erfolg)
"""

import argparse
import contextlib
import json
import queue
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image

from app import d30, mqttmini, printmq

Sender = Callable[[list[Image.Image]], None]


def handle_job(raw: bytes, send: Sender) -> dict[str, Any]:
    """Auftrag ausführen; liefert die Ergebnisnachricht (nie eine Ausnahme)."""
    job_id = ""
    try:
        job = json.loads(raw)
        if not isinstance(job, dict):
            raise ValueError("Auftrag muss ein JSON-Objekt sein")
        job_id = str(job.get("id", ""))
        images = printmq.decode_job(job)
        send(images)
        return {"id": job_id, "ok": True, "printed": len(images)}
    except Exception as exc:  # Fehler als Ergebnis melden, Agent läuft weiter
        return {"id": job_id, "ok": False, "error": str(exc)[:160]}


def status_message(dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"online": True, "available": True, "msg": "Probelauf (kein Drucker)"}
    ok, msg = d30.status()
    return {"online": True, "available": ok, "msg": msg}


def run(args: argparse.Namespace) -> None:
    password = Path(args.password_file).read_text(encoding="utf-8-sig").strip()
    will = mqttmini.Will(printmq.T_STATUS, json.dumps({"online": False}).encode())
    send: Sender = (lambda images: None) if args.dry_run else d30.send
    jobs: queue.Queue[bytes] = queue.Queue()
    stop = threading.Event()

    def worker(c_ref: list[mqttmini.Client]) -> None:
        while not stop.is_set():
            try:
                raw = jobs.get(timeout=1)
            except queue.Empty:
                continue
            result = handle_job(raw, send)
            print(time.strftime("%H:%M:%S"), "Auftrag", result, flush=True)
            for c in c_ref:  # aktuelle Verbindung
                with contextlib.suppress(OSError, mqttmini.MqttError):
                    c.publish(printmq.T_RESULT, json.dumps(result))

    current: list[mqttmini.Client] = []
    threading.Thread(target=worker, args=(current,), daemon=True).start()
    while True:
        c = mqttmini.Client(args.broker, args.port, args.user, password, "kp-desktop-print",
                            will=will)  # fmt: skip
        try:
            c.connect()
            current[:] = [c]
            c.subscribe(printmq.T_QUEUE)
            c.publish(printmq.T_STATUS, json.dumps(status_message(args.dry_run)), retain=True)
            print("Druck-Agent verbunden mit", args.broker, flush=True)
            last = time.monotonic()
            while True:
                msg = c.poll(1.0)
                if msg and msg[0] == printmq.T_QUEUE:
                    jobs.put(msg[1])
                if time.monotonic() - last > 60:  # Drucker-Status auffrischen
                    last = time.monotonic()
                    c.publish(printmq.T_STATUS, json.dumps(status_message(args.dry_run)),
                              retain=True)  # fmt: skip
        except (OSError, mqttmini.MqttError) as exc:
            print("Verbindung weg:", exc, "– neuer Versuch in 10 s", flush=True)
            current.clear()
            c.close()
            time.sleep(10)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MQTT-Druck-Agent für den D30")
    ap.add_argument("--broker", default="192.168.74.6")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default="kp-desktop-print")
    ap.add_argument("--password-file", required=True)
    ap.add_argument("--dry-run", action="store_true")
    run(ap.parse_args(argv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
