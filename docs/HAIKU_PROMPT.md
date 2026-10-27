# Erst-Inventur per Claude-Chat (Haiku)

Codes nach Schema (docs/ETIKETTEN.md): RAU-, REG-, WBA-, TBX-, EUR-, KIS-, SOR-, BOX- … + 3 Ziffern (Liste: Etiketten → Code-Schema). Teile bekommen ART-Codes automatisch beim Import (Einstellung).

Ablauf pro Behälter: Etikett aufkleben → Foto vom offenen Inhalt + kurze Sprach-/Textnotiz in den Chat → JSON-Antwort sammeln → gesammelt in `/import` einfügen.
Tipp: Ein Chat pro Raum/Regal; am Ende „Gib alle Behälter als ein JSON-Array aus“.

> In der App: Behälterseite › „Inventur per Chat (Haiku)“ › „Prompt kopieren“ – enthält schon Code/Art/Eltern des Behälters. Quelle: `app/prompt.py`.

## Prompt (einmal am Chat-Anfang einfügen)

```
Du hilfst mir bei einer Lagerinventur. Ich schicke pro Behälter: Code, Behältertyp,
übergeordneten Behälter, ein Foto und/oder eine Notiz. Antworte NUR mit JSON nach diesem Schema,
ohne Erklärtext:

{"code":"EUR-001","name":"kurzer Name","kind":"room|shelf|workbench|wall|drawer|toolbox|case|module|sortingbox|eurobox|crate|box|consumables|raw|cables|components|ppe",
 "parent":"REG-001 oder null","grid":"6x8 oder null",
 "items":[{"name":"Holzschrauben 4x40","qty":null,"qty_hint":"viele","unit":"Stk",
           "slot":"B3 oder null","tags":"schrauben holz befestigung"}]}

Regeln: Deutsche, suchbare Bezeichnungen (Gattung + Merkmal). Gleichartiges zusammenfassen.
qty nur wenn ich eine Zahl nenne oder sie eindeutig zählbar ist, sonst qty_hint ("ca. 20", "viele").
tags = 2-5 Suchbegriffe inkl. Oberbegriff und Verwendungszweck. Nichts erfinden; Unsicheres
mit "?" im Namen markieren. Wenn ich "alle" sage, gib alle bisherigen Behälter als JSON-Array aus.
```

## Hinweis
Einfügen unter `/import` (Vorschau → Übernehmen). Mehrere Antworten am Stück, auch mit ```json-Zäunen, gehen. Doppelt importierte Teile werden übersprungen, `slot` legt das Fach an. Ein späterer API-Abruf (M9) nutzt denselben Prompt. Backup: `/export.json` (voller Dump) bzw. SQLite-Datei.
