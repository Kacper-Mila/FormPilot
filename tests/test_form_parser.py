from __future__ import annotations

from src.form_parser import _has_required_marker


def test_required_marker_detects_polish_english_and_asterisk():
    assert _has_required_marker("Płeć *")
    assert _has_required_marker("Required")
    assert _has_required_marker("Wymagane")
    assert not _has_required_marker("Opcja bez znacznika")

