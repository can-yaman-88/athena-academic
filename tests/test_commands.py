"""Slash-command parser tests — the user-facing command surface."""

from __future__ import annotations

import pytest

from core.commands import parse_command


@pytest.mark.parametrize(
    "text, expected_name, expected_route",
    [
        ("/gorev rapor yaz", "gorev", "task_tool_node"),
        ("/agorev Mat analiz", "agorev", "task_tool_node"),
        ("/altgorev(3) sunum", "altgorev", "task_tool_node"),
        ("/altakademik(2) proje", "altakademik", "task_tool_node"),
        ("/seans 2 saat integral", "seans", "session_node"),
        ("/plan Final çalışması", "plan", "task_tool_node"),
        ("/aralik Bölüm 3", "aralik", "task_tool_node"),
        ("/antrenman 45dk koşu", "antrenman", "workout_tool_node"),
        ("/yardim", "yardim", "chat_node"),
    ],
)
def test_known_commands_parse(text, expected_name, expected_route):
    cmd, rest, _ = parse_command(text)
    assert cmd is not None, f"{text} did not parse"
    assert cmd.name == expected_name
    assert cmd.route == expected_route


@pytest.mark.parametrize(
    "text",
    [
        "/duzenle koşuyu uzat",
        "/complete rapor",
        "/sil market",
        "/ertele proje yarın",
        "/not rapor: bitti",
        "/default @opus",
        "/wplan haftalık plan",
    ],
)
def test_removed_commands_no_longer_parse(text):
    """The non-menu commands were removed; they must fall through to the LLM."""
    cmd, rest, _ = parse_command(text)
    assert cmd is None
    assert rest == text


def test_plain_message_is_not_a_command():
    cmd, rest, n = parse_command("merhaba nasılsın")
    assert cmd is None
    assert rest == "merhaba nasılsın"


def test_idea_count_hint_parsed():
    # The count binds directly to the command token: /fikir(3), no space.
    cmd, rest, n = parse_command("/fikir(3) yapay zeka projeleri")
    assert cmd is not None and cmd.name == "fikir"
    assert n == 3
    assert rest == "yapay zeka projeleri"
