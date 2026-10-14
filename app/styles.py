"""🎛️ Apply themes and readable focus marks."""
from functools import lru_cache

FONT_STACK = "'SF Pro Text', '.AppleSystemUIFont', 'Segoe UI Variable', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
FONT_STACK_DISPLAY = "'SF Pro Display', '.AppleSystemUIFont', 'Segoe UI Variable', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"

# Each theme is a flat dict of color tokens consumed by build_stylesheet() below.
THEMES = {
    "macos_light": {
        "label": "macOS Light",
        "bg": "#F5F5F7", "surface": "#FFFFFF", "surface_alt": "#FBFBFD",
        "border": "#E2E2E5", "border_strong": "#D8D8DC",
        "text": "#1D1D1F", "text_muted": "#6E6E73", "text_faint": "#8A8A8E",
        "accent": "#0A84FF", "accent_hover": "#0074E0", "accent_pressed": "#0064C4",
        "danger": "#E0393E", "danger_bg_hover": "#FFF1F1", "danger_border": "#F0C4C4",
        "scrollbar": "#C7C7CC", "scrollbar_hover": "#ABABB0",
        "shadow_alpha": 60,
    },
    "macos_dark": {
        "label": "macOS Dark",
        "bg": "#1E1E20", "surface": "#2C2C2E", "surface_alt": "#252527",
        "border": "#3A3A3C", "border_strong": "#48484A",
        "text": "#F5F5F7", "text_muted": "#AEAEB2", "text_faint": "#8E8E93",
        "accent": "#0A84FF", "accent_hover": "#3B9EFF", "accent_pressed": "#0064C4",
        "danger": "#FF6961", "danger_bg_hover": "#3A2323", "danger_border": "#5C3232",
        "scrollbar": "#48484A", "scrollbar_hover": "#5A5A5C",
        "shadow_alpha": 140,
    },
    "ios_light": {
        "label": "iOS Light",
        "bg": "#F2F2F7", "surface": "#FFFFFF", "surface_alt": "#FFFFFF",
        "border": "#E5E5EA", "border_strong": "#D1D1D6",
        "text": "#000000", "text_muted": "#3C3C43", "text_faint": "#8E8E93",
        "accent": "#007AFF", "accent_hover": "#0066D6", "accent_pressed": "#0055B3",
        "danger": "#FF3B30", "danger_bg_hover": "#FFEDEC", "danger_border": "#FFC7C4",
        "scrollbar": "#C7C7CC", "scrollbar_hover": "#AEAEB2",
        "shadow_alpha": 50,
    },
    "ios_dark": {
        "label": "iOS Dark",
        "bg": "#000000", "surface": "#1C1C1E", "surface_alt": "#171719",
        "border": "#38383A", "border_strong": "#48484A",
        "text": "#FFFFFF", "text_muted": "#AEAEB2", "text_faint": "#8E8E93",
        "accent": "#0A84FF", "accent_hover": "#409CFF", "accent_pressed": "#0064C4",
        "danger": "#FF453A", "danger_bg_hover": "#331F1E", "danger_border": "#5C2E2B",
        "scrollbar": "#3A3A3C", "scrollbar_hover": "#4E4E50",
        "shadow_alpha": 160,
    },
    "graphite": {
        "label": "Graphite",
        "bg": "#EDEDED", "surface": "#FAFAFA", "surface_alt": "#F3F3F3",
        "border": "#DBDBDB", "border_strong": "#C9C9C9",
        "text": "#1C1C1E", "text_muted": "#5C5C5E", "text_faint": "#8A8A8A",
        "accent": "#5A5A5E", "accent_hover": "#454547", "accent_pressed": "#333335",
        "danger": "#C0392B", "danger_bg_hover": "#FBEAE8", "danger_border": "#E7C3BE",
        "scrollbar": "#C4C4C4", "scrollbar_hover": "#A6A6A6",
        "shadow_alpha": 55,
    },
    "midnight_blue": {
        "label": "Midnight Blue",
        "bg": "#0F1620", "surface": "#182233", "surface_alt": "#131C29",
        "border": "#26344A", "border_strong": "#324361",
        "text": "#EAF1FB", "text_muted": "#9FB1CC", "text_faint": "#71839E",
        "accent": "#4C9CFF", "accent_hover": "#6FB1FF", "accent_pressed": "#3B82E0",
        "danger": "#FF6E6E", "danger_bg_hover": "#2C1B22", "danger_border": "#4A2A32",
        "scrollbar": "#324361", "scrollbar_hover": "#3F5578",
        "shadow_alpha": 150,
    },
    "sandstone": {
        "label": "Sandstone",
        "bg": "#F4EEE4", "surface": "#FFFCF6", "surface_alt": "#FAF4EA",
        "border": "#E6DAC4", "border_strong": "#D8C7A6",
        "text": "#3B3226", "text_muted": "#7A6D57", "text_faint": "#A0937A",
        "accent": "#B4682B", "accent_hover": "#985A24", "accent_pressed": "#7C481D",
        "danger": "#B3382C", "danger_bg_hover": "#FBECE8", "danger_border": "#E9C6BE",
        "scrollbar": "#D8C7A6", "scrollbar_hover": "#C3AE86",
        "shadow_alpha": 55,
    },
    "forest": {
        "label": "Forest",
        "bg": "#EFF4EE", "surface": "#FBFDFA", "surface_alt": "#F3F8F1",
        "border": "#D6E5D2", "border_strong": "#BFD8BA",
        "text": "#1E2E1B", "text_muted": "#4F6B49", "text_faint": "#7C9375",
        "accent": "#2E8B57", "accent_hover": "#257146", "accent_pressed": "#1F5F39",
        "danger": "#C0392B", "danger_bg_hover": "#FBEAE8", "danger_border": "#E7C3BE",
        "scrollbar": "#BFD8BA", "scrollbar_hover": "#A2C69B",
        "shadow_alpha": 55,
    },
    "lavender": {
        "label": "Lavender",
        "bg": "#F3F1FA", "surface": "#FFFFFF", "surface_alt": "#F8F6FD",
        "border": "#E2DCF5", "border_strong": "#D0C6EE",
        "text": "#2B2440", "text_muted": "#655C82", "text_faint": "#8D82AA",
        "accent": "#8355E8", "accent_hover": "#7141D6", "accent_pressed": "#5E30BE",
        "danger": "#D14E5B", "danger_bg_hover": "#FCEBEC", "danger_border": "#F0C6C9",
        "scrollbar": "#D0C6EE", "scrollbar_hover": "#B6A6E0",
        "shadow_alpha": 55,
    },
    "high_contrast": {
        "label": "High Contrast",
        "bg": "#FFFFFF", "surface": "#FFFFFF", "surface_alt": "#F0F0F0",
        "border": "#000000", "border_strong": "#000000",
        "text": "#000000", "text_muted": "#000000", "text_faint": "#3A3A3A",
        "accent": "#0000EE", "accent_hover": "#0000C4", "accent_pressed": "#00009B",
        "danger": "#D40000", "danger_bg_hover": "#FFE0E0", "danger_border": "#D40000",
        "scrollbar": "#000000", "scrollbar_hover": "#333333",
        "shadow_alpha": 90,
    },
    "seafoam": {
        "label": "Seafoam",
        "bg": "#EAF6F4", "surface": "#FFFFFF", "surface_alt": "#F2FAF8",
        "border": "#D3EAE5", "border_strong": "#BFDFD9",
        "text": "#173832", "text_muted": "#4C7A71", "text_faint": "#7FA69D",
        "accent": "#12A594", "accent_hover": "#0E8A7C", "accent_pressed": "#0B7266",
        "danger": "#C0392B", "danger_bg_hover": "#FBEAE8", "danger_border": "#E7C3BE",
        "scrollbar": "#BFDFD9", "scrollbar_hover": "#9FCEC5",
        "shadow_alpha": 55,
    },
    "carbon": {
        "label": "Carbon",
        "bg": "#0A0A0B", "surface": "#161617", "surface_alt": "#121213",
        "border": "#2A2A2C", "border_strong": "#38383A",
        "text": "#F2F2F3", "text_muted": "#A5A5A8", "text_faint": "#79797C",
        "accent": "#FF9F0A", "accent_hover": "#FFB13D", "accent_pressed": "#E08B00",
        "danger": "#FF6961", "danger_bg_hover": "#3A2323", "danger_border": "#5C3232",
        "scrollbar": "#38383A", "scrollbar_hover": "#48484A",
        "shadow_alpha": 150,
    },
}

THEME_ORDER = [
    "macos_light", "macos_dark", "ios_light", "ios_dark", "graphite",
    "midnight_blue", "sandstone", "forest", "lavender", "high_contrast",
    "seafoam", "carbon",
]

DEFAULT_THEME = "macos_light"


def theme_labels():
    """Return [(theme_id, display_label), ...] in a fixed, sensible order."""
    return [(tid, THEMES[tid]["label"]) for tid in THEME_ORDER]


def theme_colors(theme_id: str) -> dict:
    return THEMES.get(theme_id, THEMES[DEFAULT_THEME])


def build_stylesheet(theme_id: str, focus_outlines: bool = True, larger_click_targets: bool = False) -> str:
    # Cached per (theme_id, focus_outlines, larger_click_targets) triple:
    # Settings' theme swatches live-preview by calling this (via
    # MainWindow._apply_theme) on every single click, and there are only
    # 10 themes x 2 focus-outline states x 2 click-target states --
    # caching the built QSS string means re-selecting a theme (or
    # clicking through several) skips rebuilding the whole stylesheet
    # string from scratch each time, leaving app.setStyleSheet()'s own
    # parse as the only remaining (unavoidable) cost. THEMES/THEME_ORDER
    # are static module-level data, so a cached string for a given
    # (theme_id, focus_outlines, larger_click_targets) triple never goes
    # stale.
    return _build_stylesheet_cached(theme_id, focus_outlines, larger_click_targets)


@lru_cache(maxsize=None)
def _build_stylesheet_cached(theme_id: str, focus_outlines: bool = True, larger_click_targets: bool = False) -> str:
    t = THEMES.get(theme_id, THEMES[DEFAULT_THEME])
    focus_rule = f"""
QPushButton:focus, QToolButton:focus, QComboBox:focus, QLineEdit:focus,
QTextEdit:focus, QCheckBox:focus, QTabBar::tab:focus {{
    border: 1px solid {t['accent']};
}}
#ThemeSwatch:focus {{
    border: 1px solid {t['accent']};
}}
""" if focus_outlines else ""
    # Larger click/touch targets (Accessibility): a plain additive rule
    # block appended after the base sheet below, so it wins via normal
    # CSS cascade (later rule wins on equal specificity) without having
    # to duplicate or edit every individual button/checkbox rule above.
    click_target_rule = f"""
QPushButton, #IconButton {{
    padding: 10px 18px;
    min-height: 22px;
}}
QCheckBox::indicator {{
    width: 20px;
    height: 20px;
}}
#IconButton {{
    min-width: 36px;
    min-height: 36px;
}}
#CardTypeBadge, #CardPriorityBadge {{
    padding: 8px 12px;
}}
#CardSelectCheckbox::indicator {{
    width: 20px;
    height: 20px;
}}
#CardMenuButton {{
    min-width: 32px;
    min-height: 32px;
}}
""" if larger_click_targets else ""
    return f"""
QWidget {{
    background-color: {t['bg']};
    font-family: {FONT_STACK};
    font-size: 14px;
    color: {t['text']};
}}

/* Labels have no visual "surface" of their own -- they should always show
   whatever container they're sitting on (a toolbar, a card, a column),
   never their own opaque background. Without this, every QLabel picks up
   the generic QWidget background-color above and paints a visible box
   behind its text whenever it sits on a differently-colored parent. */
/* Icon-style tool buttons (card menu "...", column left/right/menu, the
   settings gear) have no surface of their own -- like QLabel, they should
   always show whatever they're sitting on (a card, a column header, the
   toolbar) rather than the OS-default button chrome, which renders as an
   opaque dark box that clashes with light card colors and dark themes
   alike. #IconButton (the settings gear) keeps its own hover treatment
   defined below. */
QToolButton {{
    background: transparent;
    border: none;
    color: {t['text_muted']};
    font-weight: 700;
}}
QToolButton:hover {{
    background-color: rgba(0,0,0,0.06);
    border-radius: 6px;
}}
QToolButton::menu-indicator {{
    image: none;
    width: 0px;
}}

QLabel {{
    background: transparent;
}}

QMainWindow {{
    background-color: {t['bg']};
}}

/* Top toolbar - iOS/macOS "control center" translucent bar feel.
   #TopBarScroll is the frameless QScrollArea #TopBar sits inside (see
   MainWindow._build_ui) so a narrow window scrolls the toolbar instead of
   compressing/clipping its buttons; it must stay borderless/transparent
   itself so it reads as one seamless bar with #TopBar rather than a
   visibly separate framed panel. */
#TopBar, #TopBarScroll, #TopBarScroll > QWidget > QWidget {{
    background-color: {t['surface']};
}}
#TopBarScroll {{
    border: none;
    border-bottom: 1px solid {t['border']};
}}

#AppTitle {{
    background: transparent;
    font-family: {FONT_STACK_DISPLAY};
    font-size: 17px;
    font-weight: 700;
    color: {t['text']};
    letter-spacing: 0.2px;
}}

#ProjectSelector {{
    padding: 6px 10px;
    border-radius: 9px;
    border: 1px solid {t['border_strong']};
    background: {t['surface']};
    min-width: 170px;
    color: {t['text']};
    font-weight: 700;
}}
#ProjectSelector::drop-down {{
    border: none;
    width: 22px;
}}
#ProjectSelector::down-arrow {{
    width: 9px;
    height: 9px;
}}
#ProjectSelector QAbstractItemView {{
    background-color: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    outline: none;
    padding: 4px;
    selection-background-color: {t['accent']};
    selection-color: white;
    color: {t['text']};
    font-weight: 700;
}}

QPushButton {{
    background-color: {t['surface']};
    border: 1px solid {t['border_strong']};
    border-radius: 9px;
    padding: 6px 14px;
    color: {t['text']};
    font-weight: 700;
}}
QPushButton:hover {{
    background-color: {t['surface_alt']};
}}
QPushButton:pressed {{
    background-color: {t['border']};
}}

#PrimaryButton {{
    background-color: {t['accent']};
    color: white;
    border: none;
    font-weight: 700;
}}
#PrimaryButton:hover {{
    background-color: {t['accent_hover']};
}}
#PrimaryButton:pressed {{
    background-color: {t['accent_pressed']};
}}

#DangerButton {{
    background-color: {t['surface']};
    color: {t['danger']};
    border: 1px solid {t['danger_border']};
}}
#DangerButton:hover {{
    background-color: {t['danger_bg_hover']};
}}

#IconButton {{
    border: none;
    background: transparent;
    border-radius: 10px;
    padding: 2px 6px;
    font-size: 19px;
    min-width: 28px;
    min-height: 28px;
}}
#IconButton:hover {{
    background-color: {t['surface_alt']};
}}

/* Multi-select bulk-action bar (see MainWindow._build_ui) */
#SelectionBar {{
    background-color: {t['accent']};
    border: none;
}}
#SelectionBarLabel {{
    color: white;
    font-weight: 700;
    background: transparent;
}}
#SelectionBar QPushButton {{
    background-color: rgba(255, 255, 255, 40);
    color: white;
    border: 1px solid rgba(255, 255, 255, 90);
    border-radius: 9px;
    padding: 6px 14px;
}}
#SelectionBar QPushButton:hover {{
    background-color: rgba(255, 255, 255, 70);
}}
#SelectionBar QToolButton {{
    color: white;
    background: transparent;
    border: none;
    font-size: 16px;
    font-weight: 700;
    padding: 4px 8px;
}}
#SelectionBar QToolButton:hover {{
    background-color: rgba(255, 255, 255, 40);
    border-radius: 6px;
}}

/* Board area */
#BoardScrollArea {{
    border: none;
    background-color: {t['bg']};
}}

#BoardCanvas {{
    background-color: {t['bg']};
}}

/* Column */
#ColumnFrame {{
    background-color: {t['surface_alt']};
    border: 1px solid {t['border']};
    border-radius: 14px;
}}

/* Drag-feedback border and the column accent stripe are both applied via
   an inline per-instance stylesheet on the ColumnWidget itself (see
   column_widget.ColumnWidget._apply_accent_color) rather than a QSS state
   selector here: each column needs its own accent color, which a single
   shared #ColumnFrame rule can't parameterize per-instance, and an inline
   stylesheet always wins over any QSS rule for the same widget/selector
   -- so a rule here would be silently shadowed the moment a column has an
   accent color, which is now always. */

#ColumnHeader {{
    background: transparent;
    font-family: {FONT_STACK_DISPLAY};
    font-size: 14px;
    font-weight: 700;
    color: {t['text']};
    padding: 4px 2px;
}}

#ColumnCount {{
    background: transparent;
    color: {t['text_faint']};
    font-weight: 500;
}}

#ColumnDragHandle {{
    background: transparent;
    color: {t['text_faint']};
    font-size: 14px;
    padding-right: 2px;
}}

/* Inline quick-add field: a compact single-line entry sitting directly
   under the column header, styled as a small, understated sibling of
   #ColumnTypeFilter just below it -- same rounded/bordered treatment so
   the two read as a matched pair of small controls, not one field that
   looks native-Qt next to one that's themed. */
#QuickAddEdit {{
    padding: 5px 8px;
    border-radius: 7px;
    border: 1px solid {t['border']};
    background: {t['surface']};
    color: {t['text']};
    font-size: 12px;
    font-weight: 600;
}}
#QuickAddEdit:focus {{
    border: 1px solid {t['accent']};
}}

/* Per-column card-type filter combo box, styled as a small, understated
   sibling of #ProjectSelector -- smaller padding/font since it sits
   inside the narrow column header area rather than the top bar, and it's
   one of many (one per column) rather than a single prominent control. */
#ColumnTypeFilter {{
    padding: 3px 8px;
    border-radius: 7px;
    border: 1px solid {t['border']};
    background: {t['surface']};
    color: {t['text_muted']};
    font-size: 11px;
    font-weight: 700;
}}
#ColumnTypeFilter::drop-down {{
    border: none;
    width: 18px;
}}
#ColumnTypeFilter::down-arrow {{
    width: 8px;
    height: 8px;
}}
#ColumnTypeFilter QAbstractItemView {{
    background-color: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    outline: none;
    padding: 4px;
    selection-background-color: {t['accent']};
    selection-color: white;
    color: {t['text']};
    font-weight: 700;
}}

/* Sort direction toggle (the small up/down-arrow button beside "Sort
   by" -- see #ColumnSortDirButton in column_widget.py), styled as a
   compact bordered sibling of #ColumnTypeFilter right next to it, rather
   than the borderless QToolButton look used elsewhere -- it needs to
   read as a distinct clickable control at a glance, not blend into the
   column header the way icon-only buttons like the "+"/"..." ones do. */
#ColumnSortDirButton {{
    border: 1px solid {t['border']};
    border-radius: 7px;
    background: {t['surface']};
    color: {t['text_muted']};
    font-weight: 700;
    padding: 3px 6px;
}}
#ColumnSortDirButton:hover {{
    background-color: {t['surface_alt']};
    border-color: {t['border_strong']};
}}
#ColumnSortDirButton:disabled {{
    color: {t['text_faint']};
}}

#ColumnDropZone {{
    background: transparent;
}}
#ColumnDropZone[alwaysHighlighted="true"] {{
    border: 1px dashed {t['border']};
    border-radius: 8px;
}}

/* Empty-state placeholder shown when a column (or the active type
   filter within it) has no cards to display -- see
   column_widget.ColumnWidget._show_empty_state. Muted/understated by
   design so it reads as a hint rather than competing visually with
   actual cards once any are added. */
#ColumnEmptyStateIcon {{
    background: transparent;
    font-size: 28px;
}}
#ColumnEmptyStateLabel {{
    background: transparent;
    color: {t['text_faint']};
    font-size: 12px;
    font-weight: 600;
}}
#ColumnEmptyStateCta {{
    color: {t['accent']};
    border: 1px dashed {t['border']};
    border-radius: 8px;
    background: transparent;
    font-weight: 700;
    font-size: 12px;
    padding: 6px 12px;
}}
#ColumnEmptyStateCta:hover {{
    color: white;
    background-color: {t['accent']};
    border: 1px solid {t['accent']};
}}

#ColumnScrollArea, #ColumnScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

#ColumnDropZone[dragOver="true"] {{
    background-color: {t['surface']};
    border-radius: 8px;
}}

#ColumnDropIndicator {{
    background-color: {t['accent']};
    border-radius: 2px;
}}

/* Add-card control now lives in the column header as a small "+" icon
   button (see column_widget.ColumnWidget) instead of a full-width
   "+ Add Card" text button under the card list. */
#AddCardButton {{
    color: {t['accent']};
    border: none;
    background: transparent;
    font-weight: 700;
    font-size: 15px;
    padding: 2px;
    min-width: 22px;
    min-height: 22px;
}}
#AddCardButton:hover {{
    color: white;
    background-color: {t['accent']};
    border-radius: 6px;
}}

/* Feature card - "laminated paper" look (colors set per-card in code) */
#FeatureCard {{
    border-radius: 12px;
    border: 1px solid rgba(0,0,0,0.08);
}}

/* Card note surfaces always render on a light "laminated paper" background
   (colors set per-card in code, see card_widget._apply_color), regardless of
   the active app theme -- so these use fixed near-black/dark tones rather
   than theme text tokens, which could be near-white in dark themes and
   become unreadable against the light card background. */
#CardTitle {{
    background: transparent;
    font-weight: 700;
    font-size: 13px;
    color: #1D1D1F;
    qproperty-alignment: AlignCenter;
}}

#CardDesc {{
    background: transparent;
    font-weight: 700;
    color: #3A3A3E;
    font-size: 12px;
    qproperty-alignment: AlignCenter;
}}

/* Type badge is a QToolButton (see card_widget.FeatureCardWidget) rather
   than a plain label, so it has a real clickable hit area for its quick
   "change type" menu. Padding here is deliberately generous compared to
   the old label's tight 2px/6px box -- the extra padding IS the bigger
   hit area, not just visual breathing room -- and border: none clears
   QToolButton's default frame so it still reads as the same flat pill
   the label used to be. */
#CardTypeBadge {{
    font-size: 10px;
    font-weight: 700;
    border-radius: 6px;
    border: none;
    padding: 5px 9px;
    background-color: rgba(0,0,0,0.08);
    color: #2E2E30;
}}
#CardTypeBadge::menu-indicator {{
    image: none;
    width: 0px;
}}
#CardTypeBadge:hover {{
    background-color: rgba(0,0,0,0.16);
}}

#CardNumber {{
    background: transparent;
    font-size: 10px;
    font-weight: 600;
    color: rgba(0,0,0,0.4);
}}

/* Priority badge -- background color is set per-card inline (see
   card_widget._build_ui, models.PRIORITY_COLORS), same pattern as
   #FeatureCard's own per-card background. Kept visually distinct from
   #CardTypeBadge (pill shape, white text) so priority and type never
   read as the same kind of tag at a glance. */
#CardPriorityBadge {{
    font-size: 10px;
    font-weight: 700;
    border-radius: 6px;
    border: none;
    padding: 5px 9px;
    color: white;
}}
#CardPriorityBadge::menu-indicator {{
    image: none;
    width: 0px;
}}
#CardPriorityBadge:hover {{
    /* Slight darken-on-hover independent of each card's own inline
       per-priority background-color (see card_widget._build_ui) --
       a flat black overlay at low alpha darkens any of the priority
       colors consistently without needing a per-level hover rule. */
    background-color: rgba(0,0,0,0.15);
}}

/* Card menu button ("...") sits on the laminated card surface like the
   other card elements above, so it needs the same fixed dark tone rather
   than the theme-driven QToolButton color, which would be unreadable
   (near-white) against the light card in dark themes. */
#CardMenuButton {{
    background: transparent;
    border: none;
    color: #2E2E30;
}}
#CardMenuButton:hover {{
    background-color: rgba(0,0,0,0.08);
    border-radius: 6px;
}}

/* Selection checkbox sits on the laminated card surface, same reasoning
   as #CardMenuButton above: fixed dark-on-light tones rather than
   theme-driven ones, since the card's own background stays light-pastel
   regardless of the active app theme. */
#CardSelectCheckbox {{
    background: transparent;
    spacing: 0px;
}}
#CardSelectCheckbox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1.5px solid rgba(0,0,0,0.35);
    background: rgba(255,255,255,0.55);
}}
#CardSelectCheckbox::indicator:checked {{
    background-color: #0A84FF;
    border: 1.5px solid #0A84FF;
}}

QLineEdit, QTextEdit, QComboBox, QSpinBox {{
    background-color: {t['surface']};
    border: 1px solid {t['border_strong']};
    border-radius: 9px;
    padding: 6px 8px;
    selection-background-color: {t['accent']};
    color: {t['text']};
}}
/* Dropdown (combo box) text is bold, both the closed field's current
   value and the popup list items -- this rule is scoped to QComboBox
   only (not QLineEdit/QTextEdit above), since free-text fields like card
   titles/descriptions were never part of the "dropdown text" ask and
   bolding them would be an unrelated, unrequested style change. */
QComboBox {{
    font-weight: 700;
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {t['accent']};
}}

/* Font-size field in the card description rich-text toolbar: the native
   spin-button arrows are already turned off in code (setButtonSymbols),
   this drops the boxed border/padding the shared QSpinBox rule above would
   otherwise still paint around it, so it reads as a plain inline number
   field rather than a boxed control. */
#FontSizeSpin {{
    border: none;
    border-radius: 0px;
    padding: 2px 0px;
    background: transparent;
}}
#FontSizeSpin:focus {{
    border: none;
}}

/* Combo box popup (project selector, card-type picker, etc.) -- rounded to
   match the rest of the "control center" style instead of the OS-default
   square popup list. */
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    width: 9px;
    height: 9px;
}}
QComboBox QAbstractItemView {{
    background-color: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    outline: none;
    padding: 4px;
    selection-background-color: {t['accent']};
    selection-color: white;
    color: {t['text']};
    font-weight: 700;
}}

QCheckBox {{
    spacing: 8px;
}}

QDialog {{
    background-color: {t['surface_alt']};
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    width: 10px;
    height: 10px;
    margin: 0px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {t['scrollbar']};
    border-radius: 5px;
    min-height: 20px;
    min-width: 20px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {t['scrollbar_hover']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}

QMenu {{
    background-color: {t['surface']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    padding: 4px;
}}
/* Symmetric left/right item padding (was 6px 20px: a wide 20px right-hand
   margin with nothing in it, since these context menus never show a
   submenu arrow or shortcut/checkmark column that would need that space
   reserved) -- QMenu already sizes its popup to its widest item's
   sizeHint, so the lopsided padding alone was what produced a visible
   strip of dead space to the right of the item text in every menu
   (column "..." menu, card "..." menu). */
QMenu::item {{
    padding: 6px 14px;
    border-radius: 6px;
    color: {t['text']};
    font-weight: 700;
}}
QMenu::item:selected {{
    background-color: {t['surface_alt']};
}}

QTabWidget::pane {{
    border: 1px solid {t['border']};
    border-radius: 10px;
    top: 4px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: {t['surface']};
    border: 1px solid {t['border_strong']};
    border-radius: 9px;
    padding: 6px 14px;
    margin-right: 6px;
    color: {t['text_muted']};
    font-weight: 500;
}}
QTabBar::tab:hover {{
    background-color: {t['surface_alt']};
}}
QTabBar::tab:selected {{
    background-color: {t['accent']};
    border: 1px solid {t['accent']};
    color: white;
    font-weight: 600;
}}

#ThemeSwatch {{
    border-radius: 10px;
    border: 2px solid transparent;
}}
#ThemeSwatch[selected="true"] {{
    border: 2px solid {t['accent']};
}}

#ChangelogVersion {{
    font-family: {FONT_STACK_DISPLAY};
    font-weight: 700;
    font-size: 13px;
    color: {t['text']};
}}
#ChangelogDate {{
    color: {t['text_faint']};
    font-size: 11px;
}}
#ChangelogCategory {{
    font-family: {FONT_STACK_DISPLAY};
    font-weight: 700;
    font-size: 12px;
    color: {t['accent']};
    padding-top: 4px;
}}
{focus_rule}{click_target_rule}"""


# Backward-compatible module-level default so any code that still imports
# `styles.APP_STYLESHEET` directly (e.g. a stale reference) keeps working.
APP_STYLESHEET = build_stylesheet(DEFAULT_THEME)
