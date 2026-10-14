"""🧪 Isolate tests from real user data."""
import os
import sys
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

@pytest.fixture(autouse=True)
def isolated_data(monkeypatch, tmp_path):
    monkeypatch.setenv('WHITEBOARD_DATA_DIR', str(tmp_path / 'data'))

@pytest.fixture
def board(qtbot, tmp_path):
    from storage import Storage
    from main_window import MainWindow
    window = MainWindow(Storage(tmp_path / 'board'))
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(60)
    return window
