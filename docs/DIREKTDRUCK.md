# Direktdruck auf den D30 – Machbarkeit (Stand 2026-10-29)

**Ergebnis: technisch möglich, aber nur mit Aufwand und Einschränkungen. Noch nicht umgesetzt.**
Der XLSX-Export (40×12) bleibt der verlässliche Weg.

## Was dafür spricht
- Der D30 spricht Bluetooth LE mit einem bekannten, per Mitschnitt entschlüsselten Protokoll
  (Rust-Crate `d30`, Python-Projekt `polskafan/phomemo_d30`): Raster-Bitmap (96 Punkte Breite für
  12 mm Band) plus Kopf-/Fußbefehle.
- Die App liefert die Etiketten ohnehin als Bild (QR + Text, 40×12 mm bei 203 dpi ≈ 320×96 px).

## Was dagegen spricht
- **Web Bluetooth** geht nur in Chrome/Edge (Android, Windows, macOS) und braucht HTTPS (ist
  vorhanden). **iPhone/Safari scheidet aus.**
- Das Gerät muss per Knopfdruck „gekoppelt“ werden (Nutzergeste), Verbindungsabbrüche und
  Firmware-Unterschiede (D30 vs. D30S/D35) sind realistisch; einen fertigen Web-Bluetooth-Treiber
  für den D30 habe ich nicht gefunden.
- Alternative auf dem PC: kleines Python-Skript mit `bleak` (BLE) auf KP-DESKTOP, das die Warteschlange
  direkt druckt. Unabhängig vom Handy-Browser, aber braucht Bluetooth am PC.

## Empfohlener Weg
1. Prototyp als Skript `tools/d30_print.py` (bleak): Warteschlange `/labels/queue` laden, Bild rendern,
   per BLE senden. Erst am echten Gerät testen.
2. Wenn zuverlässig: Knopf „Direkt drucken“ in der Warteschlange (Server ruft das Skript auf).
3. Web Bluetooth nur, wenn vom Handy aus gedruckt werden soll (Android/Chrome).

## Quellen
- Hackaday zu Thermodruckern mit gemeinsamem Protokoll: https://hackaday.com/2026/03/09/reverse-engineering-the-bluetooth-fichero-thermal-label-printer-protocol
- Rust-Treiber `d30`: https://docs.rs/crate/d30/latest
