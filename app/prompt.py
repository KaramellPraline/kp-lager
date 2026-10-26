"""Inventur-Prompt für den Haiku-Chat (Antwort -> /import). Quelle der Wahrheit, docs verweisen hierher."""

PROMPT = """Du hilfst mir bei einer Lagerinventur. Ich schicke pro Behälter: Code, Behältertyp,
übergeordneten Behälter, ein Foto und/oder eine Notiz. Antworte NUR mit JSON nach diesem Schema,
ohne Erklärtext:

{"code":"EUR-001","name":"kurzer Name","kind":"eurobox|kiste|sortierkasten|regal|raum|stapel|sonstiges",
 "parent":"REG-001 oder null","grid":"6x8 oder null",
 "items":[{"name":"Holzschrauben 4x40","qty":null,"qty_hint":"viele","unit":"Stk",
           "slot":"B3 oder null","tags":"schrauben holz befestigung"}]}

Regeln: Deutsche, suchbare Bezeichnungen (Gattung + Merkmal). Gleichartiges zusammenfassen.
qty nur wenn ich eine Zahl nenne oder sie eindeutig zählbar ist, sonst qty_hint ("ca. 20", "viele").
slot = Fach im Sortierkasten (Zeile als Buchstabe, Spalte als Zahl, z. B. B3).
tags = 2-5 Suchbegriffe inkl. Oberbegriff und Verwendungszweck. Nichts erfinden; Unsicheres
mit "?" im Namen markieren. Wenn ich "alle" sage, gib alle bisherigen Behälter als JSON-Array aus."""


def for_container(
    code: str, kind: str, name: str, parent_code: str | None, grid: str | None
) -> str:
    """Prompt + Kopfzeile für genau diesen Behälter – Foto dazu in den Chat, Antwort in /import."""
    head = f"Behälter: code={code}, kind={kind}, name={name}, parent={parent_code or 'null'}" + (
        f", grid={grid}" if grid else ""
    )
    return f"{PROMPT}\n\n{head}\nInhalt: (Foto anhängen und/oder hier beschreiben)"
