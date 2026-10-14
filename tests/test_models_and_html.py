"""🔍 Check malformed data and unsafe notes."""
import math
import pytest
from models import Project, Card, Column
from safe_html import safe_rich_text

@pytest.mark.parametrize('value', [None, [], 3, 'project'])
def test_wrong_project_shape(value):
    with pytest.raises(ValueError): Project.from_dict(value)

@pytest.mark.parametrize('key', ['columns', 'cards'])
def test_wrong_list_shape(key):
    with pytest.raises(ValueError): Project.from_dict({key: {}})


def test_duplicate_ids_and_orphans_remain_visible():
    p = Project.from_dict({'id': 'p', 'columns': [{'id': 'c', 'name': 'One'}, {'id': 'c', 'name': 'Two'}], 'cards': [{'id': 'a', 'title': 'First', 'column_id': 'c'}, {'id': 'a', 'title': 'Second', 'column_id': 'gone'}]})
    assert len(p.cards) == 2
    assert len({c.id for c in p.cards}) == 2
    assert len({c.id for c in p.columns}) == 3
    assert all(c.column_id in {col.id for col in p.columns} for c in p.cards)


def test_dates_keep_absolute_time_and_reject_bad_values():
    card = Card.from_dict({'id': 'a', 'created_at': 1729987200.5, 'updated_at': 1730000000.2, 'order': float('nan')})
    assert card.created_at == 1729987200.5
    assert card.updated_at == 1730000000.2
    assert card.order == 0
    malformed = Card.from_dict({'title': [], 'description': {}, 'card_type': [], 'created_at': 'yesterday', 'updated_at': float('inf')})
    assert malformed.title == '' and malformed.description == ''
    assert math.isfinite(malformed.created_at) and math.isfinite(malformed.updated_at)


def test_html_keeps_formatting_and_embedded_images():
    html = '<p style="font-size:18pt;font-family:Arial"><b>Plan &amp; build</b><img src="data:image/png;base64,AAAA"></p>'
    safe = safe_rich_text(html)
    assert '<b>Plan &amp; build</b>' in safe
    assert 'font-size:18pt' in safe
    assert 'data:image/png;base64,AAAA' in safe


def test_html_blocks_scripts_local_files_and_unsafe_urls():
    html = '<script>bad()</script><img src="file:///C:/private.png"><a href="javascript:bad()" onclick="bad()">Link</a><iframe src="https://evil.test">frame</iframe><p style="background:url(file:///etc/passwd)">Safe</p>'
    safe = safe_rich_text(html)
    for bad in ('bad()', 'file:', 'javascript:', 'onclick', 'iframe', 'frame', 'url('): assert bad not in safe
    assert 'Link' in safe and 'Safe' in safe
