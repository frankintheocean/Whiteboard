"""🧭 Check new task tools and their saved data."""
import base64
import copy
import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from PySide6.QtCore import Qt, QDateTime, QTimeZone
from PySide6.QtWidgets import QMessageBox
from attachments import AttachmentStore, clean_attachments, MAX_FILE_BYTES
from card_tools import clean_labels, apply_card_details, matches_card
from models import Card, Column, Project, new_id
from storage import Storage
from view_state import capture_view, apply_view, clean_view
from quick_find import QuickFindDialog, FindEntry
from card_details import CardDetails
from card_table import CardTableModel, CardFilterProxy


def test_new_fields_round_trip_and_old_defaults(tmp_path):
    store = Storage(tmp_path)
    p = Project.new_default('Project')
    c = Card('card', 'Write release', column_id=p.columns[0].id, labels=['Client', 'Release'], due_at=1900000000, reminder_at=1899996400)
    p.cards.append(c); p.columns[0].width = 400; p.view_mode = 'list'; p.view_filters = {'label': 'Client'}
    p.saved_views = [capture_view(p, {}, 'Client tasks')]
    store.add_project(p)
    restored = Storage(tmp_path).get_project(p.id)
    assert restored.to_dict() == p.to_dict()
    old = Card.from_dict({'id': 'old', 'title': 'Old card'})
    assert old.labels == [] and old.attachments == [] and old.due_at is None
    assert Column.from_dict({'id': 'old'}).width is None


def test_labels_are_distinct_and_unicode_searchable():
    assert clean_labels('Client, client, 日本語, Release') == ['Client', '日本語', 'Release']
    p = Project.new_default('日本語 project')
    c = Card('id', 'Roadmap', '<p>Résumé &amp; planning</p>', True, column_id=p.columns[0].id, labels=['Release'])
    assert matches_card(p, c, {'query': 'résumé 日本語 release'}, time.time())
    assert not matches_card(p, c, {'label': 'Missing'}, time.time())


def test_date_filters_and_edited_schedule():
    p = Project.new_default('P'); now = time.time()
    c = Card('id', 'Task', due_at=now - 5, reminder_at=now - 5, reminder_sent_at=now - 4)
    assert matches_card(p, c, {'due': 'overdue'}, now)
    assert matches_card(p, c, {'due': 'today'}, now)
    assert not matches_card(p, c, {'due': 'undated'}, now)
    apply_card_details(c, {'due_at': now + 100, 'reminder_at': now + 90})
    assert c.reminder_sent_at is None
    apply_card_details(c, {'labels': ['New']})
    assert c.due_at == now + 100


@pytest.mark.parametrize('name', ['../secret.txt', 'C:secret.txt', 'secret.exe', 'run.ps1', 'run.exe.', 'CON.txt', 'secret.txt ', 'a\\b.pdf'])
def test_unsafe_attachment_names(name):
    with pytest.raises(ValueError): clean_attachments([{'name': name, 'size': 1, 'sha256': 'a'*64}])


def test_attachment_copies_portability_and_damage(tmp_path):
    a = AttachmentStore(tmp_path / 'source-data')
    source = tmp_path / 'notes.txt'; source.write_text('Plan 日本語')
    entry = a.add(source); source.unlink()
    assert a.read(entry).decode() == 'Plan 日本語'
    p = Project.new_default('P'); p.cards = [Card('id', 'Task', column_id=p.columns[0].id, attachments=[entry])]
    exported = a.export_project(p)
    imported = Project.from_dict(exported)
    b = AttachmentStore(tmp_path / 'new-data'); b.import_project(imported, exported.get("attachment_files"))
    assert imported.cards[0].attachments == p.cards[0].attachments
    assert b.read(imported.cards[0].attachments[0]) == a.read(entry)
    opened = b.open_copy(entry); opened.write_text('Edited in another app')
    assert b.read(entry).decode() == 'Plan 日本語'
    b.path(entry).write_bytes(b'broken')
    with pytest.raises(ValueError): b.read(entry)
    b._write(entry, a.read(entry))
    assert b.read(entry) == a.read(entry)


def test_bad_attachment_payload_does_not_write_files(tmp_path):
    store = AttachmentStore(tmp_path)
    p = Project.new_default('P')
    p.cards = [Card('id', 'Card', attachments=[{'name': 'notes.txt', 'size': 1, 'sha256': 'a'*64, 'data': base64.b64encode(b'bad').decode()}])]
    with pytest.raises(ValueError): store.import_project(p)
    assert not list(store.root.glob('*'))


def test_attachment_limit(tmp_path):
    source = tmp_path / 'large.txt'
    with source.open('wb') as f: f.truncate(MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError): AttachmentStore(tmp_path / 'data').add(source)


def test_saved_view_restores_without_reordering_cards():
    p = Project.new_default('P'); p.cards = [Card('id', 'Task', column_id=p.columns[0].id, order=9)]
    p.view_filters = {'label': 'Client'}; p.columns[0].width = 410; p.columns[0].sort_key = 'priority'; p.view_mode = 'list'; p.list_sort = [4, True]
    saved = capture_view(p, {}, 'Client list')
    p.view_filters = {}; p.columns[0].width = None; p.view_mode = 'board'
    apply_view(p, saved)
    assert p.view_mode == 'list' and p.view_filters == {'label': 'Client'}
    assert p.columns[0].width == 410 and p.cards[0].order == 9 and p.list_sort == [4, True]
    assert clean_view({'name': 'Safe', 'columns': {'x': []}, 'filters': {'query': []}})['filters'] == {}


def test_search_dialog_and_command_filter(qtbot):
    chosen = []
    entries = [FindEntry('Task', 'Project A', 'task project a release', lambda: chosen.append('card')),
               FindEntry('Settings', 'Change themes', 'settings change themes', lambda: chosen.append('settings'), 'command')]
    dialog = QuickFindDialog(entries, palette=True); qtbot.addWidget(dialog)
    dialog.query.setText('project release'); assert dialog.proxy.rowCount() == 1
    dialog.query.setText('> themes'); assert dialog.proxy.rowCount() == 1
    dialog._choose(); dialog.selected_entry.callback(); assert chosen == ['settings']
    dialog.query.setText('missing'); assert dialog.proxy.rowCount() == 0


def test_card_editor_due_timezone_and_attachments(qtbot, tmp_path):
    store = AttachmentStore(tmp_path)
    details = CardDetails(['Release'], 1900000000, 1899996400, store=store); qtbot.addWidget(details)
    assert details.get_values()['due_at'] == 1900000000
    assert details.get_values()['reminder_at'] == 1899996400
    details.due_edit.setDateTime(QDateTime.fromSecsSinceEpoch(1900000000, QTimeZone(b'Pacific/Auckland')))
    assert details.get_values()['due_at'] == 1900000000
    details.due_check.setChecked(False)
    assert details.get_values()['reminder_at'] is None
    source = tmp_path / 'plan.txt'; source.write_text('Plan')
    with patch('card_details.QFileDialog.getOpenFileNames', return_value=([str(source)], '')): details.add_files()
    assert 'pending_path' in details.files[0]
    details.prepare(); assert 'pending_path' not in details.files[0]
    assert store.read(details.files[0]) == b'Plan'


def test_workspace_modes_filters_selection_and_widths(board, qtbot):
    p = board.active_project
    p.cards = [Card('a', 'Client task', column_id=p.columns[0].id, labels=['Client']), Card('b', 'Personal task', column_id=p.columns[1].id, labels=['Personal'])]
    board._refresh_all_columns()
    w = board.workspace; w.label_combo.setCurrentIndex(w.label_combo.findData('Client')); w.timer.stop(); w.apply_filters()
    assert w.proxy.rowCount() == 1
    assert sum(len(c._card_widgets) for c in board._column_widgets.values()) == 1
    w.mode.setCurrentIndex(1); assert p.view_mode == 'list'
    w.table.selectRow(0); assert board._selected_card_ids == {'a'}
    board._clear_selection(); assert not w.table.selectionModel().selectedRows()
    board._on_column_width_changed(p.columns[0].id, 440)
    assert board._column_widgets[p.columns[0].id].width() == 440
    board.resize(710, 620); qtbot.wait(50)
    assert board._column_widgets[p.columns[0].id].width() == 440
    w.reset_widths(); assert p.columns[0].width is None
    w.clear_filters(); assert w.proxy.rowCount() == 2
    assert [c.order for c in p.cards] == [0, 0]


def test_reminders_deliver_once_persist_and_reschedule(board, qtbot):
    p = board.active_project
    c = Card('reminder', 'Due task', column_id=p.columns[0].id, due_at=1000, reminder_at=900)
    p.cards.append(c); board._refresh_all_columns()
    assert board.reminders.check(950) == [(p.id, c.id)]
    assert board.reminders.check(980) == []
    assert Storage(board.storage.data_dir).get_project(p.id).cards[0].reminder_sent_at == 950
    apply_card_details(c, {'due_at': 2000, 'reminder_at': 1900})
    assert board.reminders.check(1950) == [(p.id, c.id)]


def test_duplicate_and_undo_keep_new_metadata(board, qtbot, tmp_path):
    p = board.active_project
    source = tmp_path / 'note.txt'; source.write_text('Attachment')
    entry = board.storage.attachments.add(source)
    card = Card('card', 'Task', column_id=p.columns[0].id, labels=['One'], due_at=1900000000, reminder_at=1899996400, attachments=[entry])
    p.cards.append(card); board._refresh_all_columns(); board._on_duplicate_card(card.id)
    duplicate = next(c for c in p.cards if c.id != card.id)
    assert duplicate.labels == card.labels and duplicate.labels is not card.labels
    assert duplicate.attachments == card.attachments and duplicate.attachments is not card.attachments
    assert duplicate.due_at == card.due_at
    board._undo(); assert len(p.cards) == 1
    board._redo(); assert len(p.cards) == 2


def test_large_search_uses_models(qtbot):
    entries = [FindEntry(f'Task {i}', 'Project', f'task {i} project', lambda: None) for i in range(10000)]
    dialog = QuickFindDialog(entries); qtbot.addWidget(dialog)
    dialog.query.setText('9999'); assert dialog.proxy.rowCount() == 1


def test_oled_variants_keep_black_cards_and_readable_text(board, qtbot):
    p = board.active_project; p.cards.append(Card('id', 'Task', column_id=p.columns[0].id)); board._refresh_all_columns()
    import styles
    for theme in ('oled_blue', 'oled_mint', 'oled_purple'):
        board._apply_theme(theme)
        widget = board._column_widgets[p.columns[0].id]._card_widgets['id']
        assert styles.theme_colors(theme)['bg'] == '#000000'
        assert '#000000' in widget.styleSheet()
        assert widget.graphicsEffect() is None
    board._apply_theme('macos_light')
    assert not board._column_widgets[p.columns[0].id]._card_widgets['id'].oled_mode


def test_bulk_duplicate_keeps_order_and_card_details(board, qtbot):
    p = board.active_project; column = p.columns[0].id
    p.cards = [Card('one', 'First', column_id=column, order=0, labels=['Client']), Card('two', 'Second', column_id=column, order=1, due_at=1900000000)]
    board._refresh_all_columns(); board._selected_card_ids = {'one', 'two'}
    board._bulk_duplicate_selected()
    cards = sorted(p.cards, key=lambda c: c.order)
    assert [c.title for c in cards] == ['First', 'First', 'Second', 'Second']
    assert cards[1].labels == ['Client'] and cards[3].due_at == 1900000000
    assert len(board._selected_card_ids) == 2


def test_portable_export_deduplicates_shared_files(tmp_path):
    store = AttachmentStore(tmp_path)
    source = tmp_path / 'plan.txt'; source.write_text('Shared plan')
    entry = store.add(source)
    p = Project.new_default('P')
    p.cards = [Card(str(i), f'Task {i}', column_id=p.columns[0].id, attachments=[copy.deepcopy(entry)]) for i in range(30)]
    exported = store.export_project(p)
    assert len(exported['attachment_files']) == 1
    assert all('data' not in c['attachments'][0] for c in exported['cards'])
    other = AttachmentStore(tmp_path / 'other')
    imported = Project.from_dict(exported); other.import_project(imported, exported['attachment_files'])
    assert other.read(imported.cards[-1].attachments[0]) == b'Shared plan'


def test_main_export_import_keeps_files_and_saved_view_ids(board, qtbot, tmp_path):
    p = board.active_project
    source = tmp_path / 'notes.txt'; source.write_text('Portable notes')
    p.cards = [Card('id', 'Task', column_id=p.columns[0].id, attachments=[board.storage.attachments.add(source)], labels=['Client'])]
    p.saved_views = [capture_view(p, {}, 'My view')]
    target = tmp_path / 'project.fboard.json'
    assert board._write_project_file(p, str(target))
    data = json.loads(target.read_text()); assert data['attachment_files']
    with patch('main_window.QFileDialog.getOpenFileName', return_value=(str(target), '')): board._on_import_file()
    imported = board.active_project
    assert imported.id != p.id
    assert set(imported.saved_views[0]['columns']) == {c.id for c in imported.columns}
    assert board.storage.attachments.read(imported.cards[0].attachments[0]) == b'Portable notes'


def test_saved_view_ui_restores_mode_filters_and_width(board, qtbot):
    p = board.active_project
    p.cards = [Card('id', 'Task', column_id=p.columns[0].id, labels=['Client'])]
    board._refresh_all_columns()
    p.view_mode = 'list'; p.view_filters = {'label': 'Client'}; p.columns[0].width = 430
    p.saved_views = [capture_view(p, board._column_widgets, 'Client')]
    p.view_mode = 'board'; p.view_filters = {}; p.columns[0].width = None
    board.workspace.set_project(p)
    board.workspace.restore_view(1)
    assert p.view_mode == 'list' and p.view_filters == {'label': 'Client'}
    assert board._column_widgets[p.columns[0].id].width() == 430


def test_column_drag_resize_persists_and_clamps(board, qtbot):
    from unittest.mock import Mock
    from PySide6.QtCore import QPointF
    column = board.active_project.columns[0]; widget = board._column_widgets[column.id]
    handle = widget._resize_handle
    event = Mock(); event.button.return_value = Qt.LeftButton; event.buttons.return_value = Qt.LeftButton; event.globalPosition.return_value = QPointF(100, 0)
    handle.mousePressEvent(event)
    event.globalPosition.return_value = QPointF(1000, 0); handle.mouseMoveEvent(event); handle.mouseReleaseEvent(event)
    assert column.width == 900
    assert Storage(board.storage.data_dir).get_project(board.active_project.id).columns[0].width == 900


def test_list_edit_refresh_keeps_scroll_position(board, qtbot):
    p = board.active_project
    p.cards = [Card(str(i), f'Task {i:03}', column_id=p.columns[0].id) for i in range(150)]
    board._refresh_all_columns(); board.workspace.mode.setCurrentIndex(1); qtbot.wait(70)
    bar = board.workspace.table.verticalScrollBar(); bar.setValue(50); before = bar.value()
    p.cards[-1].labels = ['Updated']; board._refresh_all_columns(); qtbot.wait(70)
    assert bar.value() == before


def test_labels_with_commas_round_trip(qtbot):
    details = CardDetails(['Client, Inc.', 'Release']); qtbot.addWidget(details)
    assert details.get_values()['labels'] == ['Client, Inc.', 'Release']


def test_tooltips_escape_user_markup_and_text_exports_keep_details(board, qtbot):
    from card_tools import plain_tooltip
    value = '<img src="file:///private.png">'
    assert '<img' not in plain_tooltip(value) and '&lt;img' in plain_tooltip(value)
    p = board.active_project
    p.cards = [Card('id', 'Task', column_id=p.columns[0].id, labels=['Client'], due_at=1900000000)]
    text = board._build_export_text(p, True)
    assert 'Labels: Client' in text and 'Due:' in text
