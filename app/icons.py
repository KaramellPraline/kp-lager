"""Icons nach Rollen (Crimson Night Core): Templates nennen nur die Rolle, nie die Ligatur.

Quelle: Material Symbols Rounded, Gewicht 300, ungefüllt (lokal in static/fonts).
`CORE` stammt 1:1 aus dem Designsystem (assets/Icons/icon-set.json); `APP` sind Lager-Rollen,
die das Designsystem noch nicht kennt – dort bei Gelegenheit nachtragen (Gruppe.Rolle → Ligatur).
"""

from markupsafe import Markup, escape

CORE = {
    "nav.home": "home", "nav.search": "search", "nav.menu": "menu", "nav.back": "arrow_back",
    "nav.forward": "arrow_forward", "nav.up": "expand_less", "nav.down": "expand_more",
    "nav.previous": "chevron_left", "nav.next": "chevron_right", "nav.close": "close",
    "nav.more": "more_horiz", "nav.more-vertical": "more_vert", "nav.overview": "dashboard",
    "nav.settings": "settings", "nav.profile": "person",
    "action.add": "add", "action.edit": "edit", "action.delete": "delete", "action.save": "save",
    "action.share": "share", "action.download": "download", "action.upload": "upload",
    "action.copy": "content_copy", "action.refresh": "refresh", "action.filter": "filter_list",
    "action.sort": "sort", "action.tune": "tune", "action.undo": "undo", "action.redo": "redo",
    "action.send": "send", "action.print": "print", "action.open": "open_in_new",
    "status.ok": "check_circle", "status.attention": "warning", "status.critical": "error",
    "status.info": "info", "status.pending": "pending", "status.help": "help",
    "content.calendar": "calendar_month", "content.time": "schedule",
    "content.history": "history", "content.place": "location_on",
    "content.document": "description", "content.folder": "folder", "content.image": "image",
    "content.attachment": "attach_file", "content.list": "format_list_bulleted",
    "content.tag": "sell", "content.inbox": "inbox", "content.favorite": "favorite",
    "content.bookmark": "bookmark", "content.star": "star",
    "data.table": "table_rows", "data.target": "flag",
    "comm.message": "chat",
    "media.play": "play_arrow", "media.pause": "pause", "media.stop": "stop",
    "media.next-track": "skip_next", "media.camera": "photo_camera", "media.mic": "mic",
    "system.lock": "lock", "system.unlock": "lock_open", "system.show": "visibility",
    "system.hide": "visibility_off", "system.sync": "sync", "system.theme-dark": "dark_mode",
    "select.check": "check", "select.checkbox-on": "check_box",
    "select.checkbox-off": "check_box_outline_blank",
}  # fmt: skip
APP = {
    "content.box": "inventory_2",  # Behälter, Lager
    "content.type": "category",  # Typ/Kategorie eines Teils
    "content.project": "assignment",  # Projekt-Sammelliste
    "content.shopping": "shopping_cart",  # Einkaufsliste
    "content.space": "grid_view",  # Freie Plätze, Raster
    "content.lent": "outbound",  # Verliehen
    "action.scan": "qr_code_scanner",  # Scannen
    "action.take": "output",  # Entnehmen
    "action.move": "move_item",  # Umlagern
    "action.ai": "smart_toy",  # Lokale KI
    "action.approve": "task_alt",  # Freigeben
    "media.dictate": "record_voice_over",  # Langes Diktat
}  # fmt: skip
ROLES = CORE | APP
SIZES = {"xs": 16, "sm": 20, "md": 24, "lg": 28, "xl": 40}


def icon(role: str, label: str = "", size: str = "md", tone: str = "") -> Markup:
    """<span class="ic">ligature</span>; ohne label dekorativ (aria-hidden)."""
    ligature = ROLES[role]  # KeyError = Tippfehler in der Rolle -> fällt in Tests auf
    px = SIZES[size]
    cls = f"ic ic-{size}" + (f" tone-{tone}" if tone else "")
    aria = f'role="img" aria-label="{escape(label)}"' if label else 'aria-hidden="true"'
    return Markup(f'<span class="{cls}" style="font-size:{px}px" {aria}>{ligature}</span>')
