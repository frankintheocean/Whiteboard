"""🔖 Read labels, dates, and card text in one place."""
import math
import csv
import io
from html import escape
from datetime import datetime
from html.parser import HTMLParser


def optional_time(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            if math.isfinite(value) and 0 <= value <= 253402300799:
                return float(value)
        except OverflowError:
            pass
    return None


def clean_labels(value):
    if isinstance(value, str):
        try:
            value = next(csv.reader([value], skipinitialspace=True, strict=True), [])
        except csv.Error as error:
            raise ValueError('Use commas between labels and close any quotes.') from error
    if not isinstance(value, list):
        return []
    labels, seen = [], set()
    for item in value:
        if isinstance(item, str):
            label = item.strip()
            if label and label.casefold() not in seen:
                labels.append(label)
                seen.add(label.casefold())
    return labels


def label_text(labels):
    stream = io.StringIO()
    csv.writer(stream).writerow(labels)
    return stream.getvalue().rstrip('\r\n')


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, value):
        self.parts.append(value)


def note_text(card):
    if not card.description_is_html:
        return card.description
    parser = _PlainText()
    parser.feed(card.description)
    return ' '.join(parser.parts)


def search_text(project, card):
    from models import priority_label
    return ' '.join((project.name, card.title, note_text(card), card.card_type,
                     priority_label(card.priority), card.priority, ' '.join(card.labels),
                     ' '.join(a.get('name', '') for a in card.attachments))).casefold()


def matches_card(project, card, filters, now):
    query = filters.get('query', '').casefold().split()
    if query and not all(word in search_text(project, card) for word in query):
        return False
    if filters.get('type') and card.card_type != filters['type']:
        return False
    priority = filters.get('priority', '')
    if priority and card.priority != ('' if priority == 'none' else priority):
        return False
    label = filters.get('label', '').casefold()
    if label and label not in [v.casefold() for v in card.labels]:
        return False
    due = filters.get('due', '')
    if due == 'overdue' and (card.due_at is None or card.due_at >= now):
        return False
    if due == 'today':
        try:
            if card.due_at is None or datetime.fromtimestamp(card.due_at).date() != datetime.fromtimestamp(now).date():
                return False
        except (ValueError, OverflowError, OSError):
            return False
    if due == 'undated' and card.due_at is not None:
        return False
    return True


def due_text(value, now=None):
    if value is None:
        return ''
    try:
        text = datetime.fromtimestamp(value).strftime('%d %b %Y, %H:%M')
    except (ValueError, OverflowError, OSError):
        return 'Date unavailable'
    return ('Overdue · ' if now is not None and value < now else '') + text


def apply_card_details(card, values):
    previous = (card.due_at, card.reminder_at)
    for key in ('due_at', 'reminder_at', 'labels', 'attachments'):
        if key in values:
            setattr(card, key, values[key])
    if (card.due_at, card.reminder_at) != previous:
        card.reminder_sent_at = None


def plain_tooltip(text):
    return '<qt>' + escape(text).replace('\n', '<br>') + '</qt>' if any(c in text for c in '<>&') else text
