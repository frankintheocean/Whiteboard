"""💽 Check saved files and recovery."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from storage import Storage, _safe_project_filename
from models import Project, Card, new_id
from file_io import atomic_write_json


def project_with_cards(count=3):
    project = Project.new_default('日本語 project 🚀')
    project.cards = [Card(new_id(), f'Card {i}', column_id=project.columns[0].id, order=i) for i in range(count)]
    return project


def test_round_trip_and_independent_defaults(tmp_path):
    first = Storage(tmp_path / 'one')
    second = Storage(tmp_path / 'two')
    first.settings['custom_card_types'].append('Research')
    assert second.settings['custom_card_types'] == []
    p = project_with_cards()
    p.cards[0].description = '<p><b>Résumé</b></p>'
    p.cards[0].description_is_html = True
    assert first.add_project(p)
    assert first.update_settings({'ui_font': 'Arial', 'reader_font_size': 19})
    restored = Storage(tmp_path / 'one')
    assert restored.projects[0].to_dict() == p.to_dict()
    assert restored.get_setting('reader_font_size') == 19


def test_only_changed_project_is_written(tmp_path):
    store = Storage(tmp_path)
    a, b = project_with_cards(), project_with_cards()
    store.add_project(a); store.add_project(b)
    original = Path(store._project_path(b.id)).read_bytes()
    with patch.object(store, '_write_project_file', wraps=store._write_project_file) as writer:
        a.cards[0].title = 'Changed'
        assert store.save_project(a.id)
        assert writer.call_count == 1
        assert writer.call_args.args[0] is a
    assert Path(store._project_path(b.id)).read_bytes() == original


def test_atomic_failure_keeps_original_and_cleans_temporary(tmp_path):
    target = tmp_path / 'saved.json'
    atomic_write_json(target, {'before': 1})
    with patch('file_io.os.replace', side_effect=OSError('disk full')):
        with pytest.raises(OSError): atomic_write_json(target, {'after': 2})
    assert json.loads(target.read_text()) == {'before': 1}
    assert list(tmp_path.glob('*.tmp')) == []


def test_failed_delete_keeps_file_until_index_is_saved(tmp_path):
    store = Storage(tmp_path)
    p = project_with_cards(); store.add_project(p)
    path = Path(store._project_path(p.id))
    with patch.object(store, '_write_index', side_effect=OSError('disk full')):
        assert not store.delete_project(p.id)
    assert path.exists()
    assert Storage(tmp_path).get_project(p.id) is not None
    assert store.save()
    assert not path.exists()


def test_failed_new_project_does_not_commit_index(tmp_path):
    store = Storage(tmp_path)
    p = project_with_cards(); store.add_project(p)
    old_index = Path(store.index_path).read_bytes()
    with patch.object(store, '_write_project_file', side_effect=OSError('disk full')):
        assert not store.add_project(project_with_cards())
    assert Path(store.index_path).read_bytes() == old_index
    assert not store.last_save_ok


def test_legacy_migration(tmp_path):
    p = project_with_cards()
    (tmp_path / 'whiteboard_data.json').write_text(json.dumps({'projects': [p.to_dict()], 'active_project_id': p.id, 'settings': {'theme': 'ios_dark'}}))
    store = Storage(tmp_path)
    assert store.get_project(p.id).to_dict() == p.to_dict()
    assert store.get_setting('theme') == 'ios_dark'
    assert (tmp_path / 'whiteboard_data.json.migrated').exists()


def test_corrupt_project_keeps_other_projects_and_backups(tmp_path):
    store = Storage(tmp_path)
    a, b = project_with_cards(), project_with_cards()
    store.add_project(a); store.add_project(b)
    target = Path(store._project_path(a.id))
    Path(str(target) + '.bak').write_text('previous recovery')
    target.write_text('{broken')
    restored = Storage(tmp_path)
    assert restored.get_project(a.id) is None
    assert restored.get_project(b.id) is not None
    assert Path(str(target) + '.bak').read_text() == 'previous recovery'
    assert Path(str(target) + '.bak.1').read_text() == '{broken'
    assert restored.recovery_messages


def test_malformed_settings_and_index_do_not_crash(tmp_path):
    store = Storage(tmp_path); p = project_with_cards(); store.add_project(p)
    index = {'project_ids': [p.id, p.id, None, {'id': 1}], 'settings': {'ui_scale': 'bad', 'custom_card_types': [[], 'Custom'], 'last_saved_paths': {'one': []}, 'reader_font_size': 999}}
    Path(store.index_path).write_text(json.dumps(index))
    restored = Storage(tmp_path)
    assert len(restored.projects) == 1
    assert restored.settings['ui_scale'] == 100
    assert restored.settings['custom_card_types'] == ['Custom']
    assert restored.settings['last_saved_paths'] == {}
    assert restored.settings['reader_font_size'] == 32


def test_unsafe_ids_are_distinct_and_stay_in_data_folder(tmp_path):
    assert _safe_project_filename('../same') != _safe_project_filename('same')
    assert _safe_project_filename('a/b') != _safe_project_filename('ab')
    store = Storage(tmp_path)
    for identifier in ('../same', 'a/b', 'ab'):
        p = project_with_cards(); p.id = identifier
        assert store.add_project(p)
        assert Path(store._project_path(p.id)).resolve().is_relative_to(tmp_path)
    assert len(Storage(tmp_path).projects) == 3


def test_large_project_round_trip(tmp_path):
    store = Storage(tmp_path)
    p = project_with_cards(10000)
    assert store.add_project(p)
    assert len(Storage(tmp_path).get_project(p.id).cards) == 10000


def test_hand_copied_project_gets_a_stable_file_name(tmp_path):
    projects = tmp_path / 'projects'; projects.mkdir()
    p = project_with_cards()
    (projects / 'copied-project.json').write_text(json.dumps(p.to_dict()))
    store = Storage(tmp_path)
    assert store.get_project(p.id) is not None
    assert store.save()
    assert Storage(tmp_path).get_project(p.id) is not None
