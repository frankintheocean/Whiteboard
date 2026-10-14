"""🖱️ Check project menus, card input, scrolling, and text settings."""
from unittest.mock import patch
import pytest
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent, QPropertyAnimation
from PySide6.QtGui import QWheelEvent, QFont, QTextCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QApplication
from PySide6.QtTest import QTest
from dialogs import FitPopupComboBox, RichTextEditor, SettingsDialog
from models import Card, new_id
from smooth_scroll import SmoothVScrollArea
from card_widget import FeatureCardWidget


def wheel(widget, amount=-120):
    event = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(), QPoint(0, amount), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget.viewport(), event)


def fill_board(board, qtbot, count=40):
    p = board.active_project
    col = p.columns[0]
    p.cards = [Card(new_id(), f'Task {i}', 'Details', column_id=col.id, order=i) for i in range(count)]
    board._refresh_all_columns()
    qtbot.wait(80)
    return board._column_widgets[col.id]


def test_project_popup_names_with_many_items(qtbot):
    combo = FitPopupComboBox(); qtbot.addWidget(combo)
    names = [f'Project {i:03} — complete descriptive project name' for i in range(150)]
    combo.addItems(names)
    combo.show(); combo.showPopup(); qtbot.wait(30)
    view = combo.view()
    widest = max(view.fontMetrics().horizontalAdvance(n) for n in names)
    assert view.viewport().width() >= widest
    assert view.textElideMode() == Qt.ElideNone
    assert combo.itemData(149, Qt.ToolTipRole) == names[149]
    assert view.window().width() <= combo.screen().availableGeometry().width()
    combo.hidePopup()


def test_very_long_project_name_scrolls_instead_of_eliding(qtbot):
    combo = FitPopupComboBox(); qtbot.addWidget(combo)
    combo.addItem('Very long project ' * 100)
    combo.show(); combo.showPopup(); qtbot.wait(30)
    assert combo.view().horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert combo.view().textElideMode() == Qt.ElideNone
    assert combo.view().window().width() < combo.screen().availableGeometry().width()
    combo.hidePopup()


def test_scroll_target_resets_after_animation_and_manual_scroll(qtbot):
    area = SmoothVScrollArea(); qtbot.addWidget(area)
    content = QWidget(); content.setMinimumSize(100, 2000)
    area.setWidget(content); area.resize(200, 200); area.show()
    wheel(area); qtbot.wait(300)
    assert area._target is None
    area.verticalScrollBar().setValue(500)
    wheel(area); qtbot.wait(300)
    assert area.verticalScrollBar().value() == 620


def test_double_click_stops_scrolling_and_opens_once(board, qtbot):
    col = fill_board(board, qtbot)
    area = col._scroll_area
    bar = area.verticalScrollBar(); bar.setValue(200)
    wheel(area); qtbot.wait(30)
    widget = next(w for w in col._card_widgets.values() if area.viewport().rect().contains(w.mapTo(area.viewport(), w.rect().center())))
    opened = []
    col.cardEditRequested.disconnect()
    col.cardEditRequested.connect(opened.append)
    QTest.mouseDClick(widget, Qt.LeftButton, pos=QPoint(10, widget.height() - 10))
    stopped = bar.value()
    qtbot.wait(280)
    assert opened == [widget.card.id]
    assert area._anim.state() != QPropertyAnimation.Running
    assert bar.value() == stopped


def test_targeted_refresh_keeps_scroll_position(board, qtbot):
    col = fill_board(board, qtbot)
    bar = col._scroll_area.verticalScrollBar()
    bar.setValue(700)
    value = bar.value()
    col._all_cards[4].title = 'Changed task'
    board._refresh_columns([col.column.id]); qtbot.wait(80)
    assert bar.value() == value


def test_card_keyboard_and_plain_title(qtbot):
    card = Card('id', '<img src="file:///private">', description='<b>Plan</b>', description_is_html=True)
    widget = FeatureCardWidget(card); qtbot.addWidget(widget); widget.show()
    edited, checked = [], []
    widget.editRequested.connect(edited.append)
    widget.checkToggled.connect(lambda identifier, value: checked.append((identifier, value)))
    QTest.keyClick(widget, Qt.Key_Return)
    QTest.keyClick(widget, Qt.Key_Space)
    assert edited == ['id'] and checked == [('id', True)]
    assert widget.title_label.textFormat() == Qt.PlainText
    assert widget.focusPolicy() == Qt.StrongFocus


def test_font_size_only_format_survives_save(qtbot):
    editor = RichTextEditor('Keep this text'); qtbot.addWidget(editor)
    cursor = editor.editor.textCursor(); cursor.select(QTextCursor.Document); editor.editor.setTextCursor(cursor)
    editor._set_font_size(20)
    assert editor.has_rich_formatting()
    assert '20pt' in editor.to_html()
    restored = RichTextEditor(editor.to_html(), is_html=True); qtbot.addWidget(restored)
    assert restored.has_rich_formatting()
    assert restored.to_plain_text() == 'Keep this text'


def test_settings_font_size_and_themes(board, qtbot):
    dialog = SettingsDialog(ui_font='Arial', reader_font_size=18); qtbot.addWidget(dialog)
    values = dialog.get_values()
    assert values['ui_font'] == 'Arial' and values['reader_font_size'] == 18
    board.storage.update_settings({'ui_font': 'Arial', 'reader_font_size': 18, 'ui_scale': 150})
    import styles
    for theme in styles.THEME_ORDER:
        board._apply_theme(theme)
        assert '"Arial"' in QApplication.instance().styleSheet()
        assert 'font-size: 27pt' in QApplication.instance().styleSheet()
    board.resize(700, 500); qtbot.wait(40)
    assert all(c.width() > 0 for c in board._column_widgets.values())


def test_drag_move_undo_redo_and_custom_types(board, qtbot):
    col = fill_board(board, qtbot, 5)
    p = board.active_project
    card = p.cards[0]; before_col = card.column_id
    target = p.columns[1].id
    board._on_card_dropped(card.id, target, 0)
    assert next(c for c in p.cards if c.id == card.id).column_id == target
    board._undo()
    assert next(c for c in p.cards if c.id == card.id).column_id == before_col
    board._redo()
    assert next(c for c in p.cards if c.id == card.id).column_id == target
    assert board.storage.rename_card_type('Add', 'Build')
    assert all(c.card_type == 'Build' for c in p.cards)
    board.storage.delete_card_type('Build', 'Fix')
    assert all(c.card_type == 'Fix' for c in p.cards)
    assert 'Build' not in board.storage.available_card_types()


def test_edit_dialog_round_trip_retains_column_offset(board, qtbot):
    col = fill_board(board, qtbot)
    p = board.active_project
    card = p.cards[12]
    bar = col._scroll_area.verticalScrollBar(); bar.setValue(900)
    offset = bar.value()
    values = {'title': 'Edited title', 'description': '<p>New <b>details</b></p>', 'description_is_html': True, 'card_type': 'Fix', 'priority': 'P1'}
    with patch('main_window.CardDialog.exec', return_value=1), patch('main_window.CardDialog.get_values', return_value=values):
        board._on_edit_card(card.id)
    qtbot.wait(100)
    assert card.title == 'Edited title' and card.priority == 'P1'
    assert bar.value() == offset
    from storage import Storage
    restored = Storage(board.storage.data_dir).get_project(p.id)
    assert next(c for c in restored.cards if c.id == card.id).description == values['description']


def test_import_makes_fresh_ids_without_overwriting(board, qtbot, tmp_path):
    import json
    from pathlib import Path
    col = fill_board(board, qtbot, 3)
    p = board.active_project
    path = tmp_path / 'import.fboard.json'; path.write_text(json.dumps(p.to_dict()))
    before = p.to_dict()
    with patch('main_window.QFileDialog.getOpenFileName', return_value=(str(path), '')):
        board._on_import_file()
    imported = board.active_project
    assert imported.id != p.id and p.to_dict() == before
    assert imported.name != p.name
    assert not {c.id for c in imported.cards} & {c.id for c in p.cards}
    assert all(c.column_id in {col.id for col in imported.columns} for c in imported.cards)


def test_failed_save_footer_and_close_guard(board, qtbot):
    from PySide6.QtWidgets import QMessageBox
    with patch.object(board.storage, '_write_index', side_effect=OSError('disk full')):
        board._save()
        assert 'not saved' in board._save_status_label.text()
        with patch('main_window.QMessageBox.warning', return_value=QMessageBox.No):
            assert not board.close()
    assert board.storage.save()
    assert 'Saved locally' in board._save_status_label.text()


def test_two_refreshes_in_one_event_turn_keep_scroll(board, qtbot):
    col = fill_board(board, qtbot)
    bar = col._scroll_area.verticalScrollBar(); bar.setValue(650)
    expected = bar.value()
    board._refresh_columns([col.column.id])
    board._refresh_columns([col.column.id])
    qtbot.wait(80)
    assert bar.value() == expected


def test_short_columns_do_not_stretch_cards_and_headers_wrap(board, qtbot):
    col = fill_board(board, qtbot, 1)
    widget = next(iter(col._card_widgets.values()))
    board.resize(760, 760); qtbot.wait(100)
    assert widget.height() < col._scroll_area.viewport().height() / 2
    assert col.header_label.wordWrap()
    assert col.header_label.textFormat() == Qt.PlainText
    assert widget.badge.toolButtonStyle() == Qt.ToolButtonTextOnly
    assert widget.badge.width() >= widget.badge.fontMetrics().horizontalAdvance(widget.badge.text())


def test_column_drop_cleanup_survives_widget_replacement(qtbot):
    import shiboken6
    from unittest.mock import Mock
    from column_widget import ColumnWidget
    from models import Column
    widget = ColumnWidget(Column('column', 'Column'))
    widget.show(); qtbot.wait(10)
    widget._drag_start_pos = QPoint(0, 0)
    event = Mock()
    event.buttons.return_value = Qt.LeftButton
    event.position.return_value = QPointF(100, 100)
    drag = Mock()
    drag.exec.side_effect = lambda action: shiboken6.delete(widget)
    with patch('column_widget.QDrag', return_value=drag):
        widget._handle_move(event)
    assert drag.exec.call_count == 1
