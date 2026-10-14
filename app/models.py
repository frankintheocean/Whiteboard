"""🧬 Define project, column, and card data."""
from dataclasses import dataclass, field, asdict
from typing import List
import uuid
import time
import math
from card_tools import optional_time, clean_labels
from attachments import clean_attachments
from view_state import clean_view, clean_filters


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _coerce_str_id(value) -> str:
    """Validate an id loaded from an external file (Open/Import). A
    well-formed file (including every file this app itself ever writes)
    always has a non-empty string id, so this is a no-op for the normal
    case. A hand-edited or corrupted file can have the wrong type (e.g. a
    JSON number) here; falling back to a fresh id rather than accepting it
    as-is avoids id collisions/type-mismatches against the string ids used
    everywhere else (Card.column_id, project/column/card lookups by id)."""
    if isinstance(value, str) and value:
        return value
    return new_id()


def _coerce_order(value) -> int:
    """Validate an 'order' loaded from an external file. Order values are
    compared with sorted(key=lambda c: c.order) throughout the app, which
    raises TypeError if the list mixes ints with strings/None/etc -- a
    single malformed entry (e.g. "order": "zero" in a hand-edited or
    corrupted file) would otherwise crash the app the moment that project
    loads. A well-formed file always has a real number here, so this is a
    no-op for the normal case; anything else falls back to 0."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return 0


def _text(value, fallback=""):
    return value if isinstance(value, str) else fallback


def _timestamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return time.time()


def _object(value):
    if not isinstance(value, dict):
        raise ValueError("Each project, column, and card must be a JSON object.")
    return value


# Built-in card types + their laminated-note colors. Users can add their own
# custom types at runtime (see storage.custom_card_types); custom types get
# assigned a color from CUSTOM_TYPE_PALETTE (cycled) so they always render
# with a distinct laminated color even though they're not hardcoded here.
CARD_TYPES = ["Add", "Change", "Remove", "Fix", "Idea"]
CARD_COLORS = {
    "Add": "#FFF7B2",      # yellow laminated note
    "Change": "#BFEFFF",   # blue
    "Remove": "#FFC9C9",   # red/pink
    "Fix": "#C8F7C5",      # green
    "Idea": "#E5D4FF",     # purple
}

CUSTOM_TYPE_PALETTE = [
    "#FFD9B3", "#D4F0C0", "#C9E4FF", "#F5D0FA", "#FFE0E9",
    "#D9D9FF", "#E0F5D8", "#FFEAAE", "#C8ECEC", "#EAD1DC",
]

# Color-blind-safe type indicators: a small glyph per built-in card type,
# shown alongside (never instead of) the existing type-badge color and
# text, so a card's type is still identifiable by shape/symbol alone for
# anyone who can't distinguish the badge colors themselves (e.g.
# red/green color blindness on Fix's green vs Remove's red/pink).
# CUSTOM_TYPE_ICONS is a small cycled fallback set for user-defined
# custom types, keyed by position the same way CUSTOM_TYPE_PALETTE is,
# so every custom type gets a distinct glyph too rather than sharing one
# generic icon.
CARD_TYPE_ICONS = {
    "Add": "\u2795",       # ➕
    "Change": "\u21BB",    # ↻
    "Remove": "\u2716",    # ✖
    "Fix": "\u2713",       # ✓
    "Idea": "\u2726",      # ✦
}
CUSTOM_TYPE_ICON_PALETTE = [
    "\u25B2", "\u25CF", "\u25A0", "\u2666", "\u2605",
    "\u25BC", "\u2B22", "\u271A", "\u2660", "\u263C",
]


def card_type_icon(card_type: str, custom_types=None) -> str:
    """Resolve the color-blind-safe glyph for a card type, mirroring
    card_type_color's own built-in/custom resolution order so a type's
    icon and color are always looked up the same way.

    custom_types is deliberately the same list callers already pass for
    card_type_color/the type menus -- it holds true user-defined custom
    types *and* any renamed built-in (see
    storage.Storage.available_card_types / MainWindow._custom_card_types),
    since a renamed built-in no longer matches its original CARD_TYPES
    key and needs a palette-cycled icon exactly like a custom type does."""
    if card_type in CARD_TYPE_ICONS:
        return CARD_TYPE_ICONS[card_type]
    if custom_types and card_type in custom_types:
        index = custom_types.index(card_type) % len(CUSTOM_TYPE_ICON_PALETTE)
        return CUSTOM_TYPE_ICON_PALETTE[index]
    return "\u25C6"  # generic diamond fallback for an unrecognized type

DEFAULT_COLUMNS = ["Backlog", "In Progress", "Review", "Done"]

# Board templates offered when creating a new project (see
# dialogs.NewProjectDialog / Project.new_default below). Each is just a
# named list of starting column names -- the same shape DEFAULT_COLUMNS
# already was, so the previous single-template behavior is simply the
# "Classic (Backlog/In Progress/Review/Done)" entry here, unchanged.
BOARD_TEMPLATES = [
    ("Classic", ["Backlog", "In Progress", "Review", "Done"]),
    ("Simple", ["To Do", "Doing", "Done"]),
    ("Bug Tracker", ["Reported", "Confirmed", "In Progress", "Fixed", "Verified"]),
    ("Kanban", ["Backlog", "Ready", "In Progress", "Blocked", "Done"]),
    ("Sprint", ["Sprint Backlog", "In Progress", "Code Review", "QA", "Done"]),
    ("Blank", []),
]
DEFAULT_TEMPLATE_NAME = "Classic"

# Priority levels a card can optionally carry, ordered highest to lowest
# urgency. Kept separate from card_type (see CARD_TYPES above): type is
# "what kind of change is this" while priority is "how urgent is it", and
# a card can combine any type with any priority (or none). None/"" means
# "no priority set", which is the default for every existing and newly
# created card unless the person explicitly picks one.
PRIORITY_LEVELS = ["P0", "P1", "P2", "P3"]
PRIORITY_COLORS = {
    "P0": "#FF3B30",  # red - critical
    "P1": "#FF9500",  # orange - high
    "P2": "#FFCC00",  # yellow - medium
    "P3": "#8E8E93",  # gray - low
}

# Display labels for each priority level (see PRIORITY_LEVELS above).
# Kept separate from the level ids themselves: PRIORITY_LEVELS' own
# "P0".."P3" values are the persisted/stored form (project files, sort
# keys, PRIORITY_COLORS lookups) and stay exactly as-is for backward
# compatibility with existing saved projects -- only the *rendered* text
# changed (P0-P3 -> High Priority..Low Priority), so this is purely a
# presentation-layer mapping consulted wherever a priority is shown to
# the person (card badge, Edit Card dialog, bulk "Set priority" menu).
PRIORITY_LABELS = {
    "P0": "High Priority",
    "P1": "Medium-High Priority",
    "P2": "Medium-Low Priority",
    "P3": "Low Priority",
}


def priority_label(level: str) -> str:
    """Resolve the display label for a priority level id, falling back to
    the raw id itself for any unrecognized value (e.g. a hand-edited or
    older/newer project file) rather than showing a blank."""
    return PRIORITY_LABELS.get(level, level)


def readable_text_color(hex_color: str) -> str:
    """Pick black or white text for readable contrast against a given
    background hex color, using the standard relative-luminance formula
    (same weighting browsers/OSes use for this kind of contrast check).
    Used for the priority badge (see PRIORITY_COLORS): several of its
    colors -- P2's bright yellow especially, P1's orange too -- are too
    light for fixed white text to stay readable on, so the badge picks
    its text color per-level instead of always using white."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "white"
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "white"
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#1C1C1E" if luminance > 0.6 else "white"


def _coerce_priority(value) -> str:
    """Validate a 'priority' loaded from an external file. A well-formed
    file has either one of PRIORITY_LEVELS or an empty string/None here;
    anything else (a hand-edited or corrupted file with a stray value)
    falls back to "" (no priority) rather than rendering an unrecognized
    badge or crashing a lookup keyed on PRIORITY_COLORS."""
    if value in PRIORITY_LEVELS:
        return value
    return ""


# Column accent colors: a small fixed palette cycled by each column's
# position (see column_accent_color below), used to paint a thin accent
# stripe per column for at-a-glance visual distinction between columns
# (see column_widget.ColumnWidget / #ColumnFrame in styles.py). Kept
# separate from CARD_COLORS/CUSTOM_TYPE_PALETTE above: those distinguish
# card *type*, this distinguishes column *position*, and the two are
# deliberately more saturated/darker than the pastel card colors so the
# stripe reads clearly against both light and dark themes without needing
# a theme-specific palette of its own.
COLUMN_ACCENT_PALETTE = [
    "#0A84FF", "#FF9F0A", "#30D158", "#FF375F", "#BF5AF2",
    "#64D2FF", "#FFD60A", "#AC8E68", "#5E5CE6", "#FF6961",
]


def column_accent_color(index: int) -> str:
    """Resolve the accent stripe color for a column, cycled by its
    position among the project's columns (in display order) rather than
    keyed by id, so accent colors stay visually stable and sequential as
    columns are added/removed/reordered instead of jumping around."""
    if not COLUMN_ACCENT_PALETTE:
        return "#0A84FF"
    return COLUMN_ACCENT_PALETTE[index % len(COLUMN_ACCENT_PALETTE)]


@dataclass
class Card:
    id: str
    title: str
    description: str = ""           # may contain rich-text HTML (see description_is_html)
    description_is_html: bool = False
    card_type: str = "Add"          # Add / Change / Remove / Fix / Idea / custom
    priority: str = ""              # "" (none) / P0 / P1 / P2 / P3 -- see PRIORITY_LEVELS
    column_id: str = ""
    order: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    due_at: float = None
    reminder_at: float = None
    reminder_sent_at: float = None
    labels: List[str] = field(default_factory=list)
    attachments: List[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        _object(d)
        return Card(
            id=_coerce_str_id(d.get("id")),
            title=_text(d.get("title")),
            description=_text(d.get("description")),
            description_is_html=d.get("description_is_html") is True,
            card_type=_text(d.get("card_type"), "Add") or "Add",
            priority=_coerce_priority(d.get("priority", "")),
            column_id=_text(d.get("column_id")),
            order=_coerce_order(d.get("order", 0)),
            created_at=_timestamp(d.get("created_at")),
            updated_at=_timestamp(d.get("updated_at")),
            due_at=optional_time(d.get("due_at")),
            reminder_at=optional_time(d.get("reminder_at")) if optional_time(d.get("due_at")) is not None else None,
            reminder_sent_at=optional_time(d.get("reminder_sent_at")),
            labels=clean_labels(d.get("labels", [])),
            attachments=clean_attachments(d.get("attachments", [])),
        )


def _coerce_sort_key(value):
    """Validate a column's persisted 'sort_key' (see Column.sort_key
    below). Only None (board order) or one of the known sort key ids is
    ever written by this app; anything else (a hand-edited or
    older/corrupted file) falls back to None (board order) rather than
    the display code choking on an unrecognized key."""
    if value in (None, "type", "priority"):
        return value
    return None


@dataclass
class Column:
    id: str
    name: str
    order: int = 0
    # This column's persisted "Sort by" choice (see column_widget.py's
    # SORT_BOARD_ORDER/SORT_BY_TYPE/SORT_BY_PRIORITY and
    # main_window._on_column_sort_state_changed). Purely a display
    # choice like the sort itself -- it never affects card.order or
    # drag/drop -- but unlike the rest of the column state it's now
    # saved to disk, so a column's sort survives closing and reopening
    # the app, not just switching projects and back within one session.
    sort_key: str = None
    sort_descending: bool = False
    width: int = None

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        _object(d)
        return Column(
            id=_coerce_str_id(d.get("id")),
            name=_text(d.get("name")),
            order=_coerce_order(d.get("order", 0)),
            sort_key=_coerce_sort_key(d.get("sort_key")),
            sort_descending=d.get("sort_descending") is True,
            width=max(220, min(900, d["width"])) if isinstance(d.get("width"), int) and not isinstance(d.get("width"), bool) else None,
        )


@dataclass
class Project:
    id: str
    name: str
    columns: List[Column] = field(default_factory=list)
    cards: List[Card] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    view_mode: str = "board"
    view_filters: dict = field(default_factory=dict)
    saved_views: List[dict] = field(default_factory=list)
    list_sort: list = field(default_factory=lambda: [0, False])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "columns": [c.to_dict() for c in self.columns],
            "cards": [c.to_dict() for c in self.cards],
            "created_at": self.created_at,
            "view_mode": self.view_mode,
            "view_filters": dict(self.view_filters),
            "saved_views": self.saved_views,
            "list_sort": self.list_sort,
        }

    @staticmethod
    def from_dict(d):
        _object(d)
        p = Project(
            id=_coerce_str_id(d.get("id")),
            name=_text(d.get("name"), "Untitled Project"),
            created_at=_timestamp(d.get("created_at")),
            view_mode="list" if d.get("view_mode") == "list" else "board",
            view_filters=clean_filters(d.get("view_filters")),
            saved_views=[state for state in (clean_view(v) for v in d.get("saved_views", [])) if state is not None] if isinstance(d.get("saved_views"), list) else [],
            list_sort=d["list_sort"] if isinstance(d.get("list_sort"), list) and len(d["list_sort"]) == 2 and isinstance(d["list_sort"][0], int) and 0 <= d["list_sort"][0] < 7 and isinstance(d["list_sort"][1], bool) else [0, False],
        )
        columns, cards = d.get("columns", []), d.get("cards", [])
        if not isinstance(columns, list) or not isinstance(cards, list):
            raise ValueError("Columns and cards must be JSON lists.")
        p.columns = [Column.from_dict(c) for c in columns]
        p.cards = [Card.from_dict(c) for c in cards]
        # Keep every entry; duplicate IDs must not alias widgets or drop targets.
        column_ids = set()
        for column in p.columns:
            if column.id in column_ids:
                column.id = new_id()
            column_ids.add(column.id)
        card_ids = set()
        recovered_column = None
        for card in p.cards:
            if card.id in card_ids:
                card.id = new_id()
            card_ids.add(card.id)
            if card.column_id not in column_ids:
                if recovered_column is None:
                    recovered_column = Column(new_id(), "Recovered cards", len(p.columns))
                    p.columns.append(recovered_column)
                    column_ids.add(recovered_column.id)
                card.column_id = recovered_column.id
        return p

    @staticmethod
    def new_default(name: str, column_names=None) -> "Project":
        """column_names: starting column names for the new project (see
        BOARD_TEMPLATES). Defaults to the classic Backlog/In Progress/
        Review/Done set -- the app's original, only template -- so every
        existing caller that doesn't pass a template keeps its exact
        prior behavior."""
        p = Project(id=new_id(), name=name)
        names = DEFAULT_COLUMNS if column_names is None else column_names
        p.columns = [Column(id=new_id(), name=n, order=i) for i, n in enumerate(names)]
        return p


def card_type_color(card_type: str, custom_types=None) -> str:
    """Resolve the laminated-note color for a card type, whether it's one
    of the built-in CARD_TYPES, a renamed built-in, or a user-defined
    custom type (see card_type_icon above for why a renamed built-in is
    resolved through the same custom_types list)."""
    if card_type in CARD_COLORS:
        return CARD_COLORS[card_type]
    custom_types = custom_types or []
    if card_type in custom_types:
        idx = custom_types.index(card_type) % len(CUSTOM_TYPE_PALETTE)
        return CUSTOM_TYPE_PALETTE[idx]
    return "#FFF7B2"
