"""Slash commands for the chatbox.

A message that begins with a known ``/word`` is handled deterministically: the
router bypasses the LLM classifier, sets the route directly, and records the
command name in the graph state so the target node can honor the command's hints
(e.g. force an academic task, force an update, treat the message as a workout
plan). The single source of truth for the command set is :data:`COMMANDS`, which
also backs the ``/yardim`` help text and the generated ``codes.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.state import RouteTarget


@dataclass(frozen=True)
class Command:
    name: str
    route: RouteTarget
    description: str
    hints: dict = field(default_factory=dict)


# name -> Command. ``hints`` is read by the target node.
COMMANDS: dict[str, Command] = {
    "akademik": Command(
        "akademik", "task_tool_node",
        "Akademik görev oluştur (AI alt türü seçer).",
        {"operation": "create", "category": "academic"},
    ),
    "proje": Command(
        "proje", "task_tool_node",
        "Akademik PROJE görevi oluştur (yönerge/materyal eklenebilir).",
        {"operation": "create", "category": "academic", "subtype": "project"},
    ),
    "odev": Command(
        "odev", "task_tool_node",
        "Akademik ÖDEV görevi oluştur.",
        {"operation": "create", "category": "academic", "subtype": "assignment"},
    ),
    "seans": Command(
        "seans", "task_tool_node",
        "Akademik ÇALIŞMA SEANSI görevi oluştur.",
        {"operation": "create", "category": "academic", "subtype": "study_session"},
    ),
    "gunluk": Command(
        "gunluk", "task_tool_node",
        "Günlük (general) görev oluştur.",
        {"operation": "create", "category": "daily"},
    ),
    "duzenle": Command(
        "duzenle", "task_tool_node",
        "Mevcut bir görevi düzenle (tarih verilmezse bugünkü, yoksa en yakın gelecekteki).",
        {"operation": "update"},
    ),
    "complete": Command(
        "complete", "task_tool_node",
        "Görevi tamamla. Biçim: /complete [tarih] <ad>. Tam ad yoksa en benzer görev.",
        {"operation": "complete"},
    ),
    "sil": Command(
        "sil", "task_tool_node",
        "Görevi sil. Biçim: /sil [tarih] <ad>. Tam ad yoksa en benzer görev.",
        {"operation": "delete"},
    ),
    "ertele": Command(
        "ertele", "task_tool_node",
        "Görevin son tarihini değiştir. Biçim: /ertele <ad> <yeni tarih/saat>.",
        {"operation": "reschedule"},
    ),
    "antrenman": Command(
        "antrenman", "workout_tool_node",
        "Tek bir antrenman ekle (süre + RPE).",
        {"mode": "single"},
    ),
    "plan": Command(
        "plan", "workout_tool_node",
        "Çoklu günlük antrenman planını içe aktar (metin ya da ekli .md/.json).",
        {"mode": "plan"},
    ),
    "not": Command(
        "not", "task_tool_node",
        "Bir göreve not ekle. Biçim: /not <görev ipucu>: <not metni>",
        {"operation": "note"},
    ),
    "yardim": Command(
        "yardim", "chat_node",
        "Komut listesini göster.",
        {"mode": "help"},
    ),
}

# A few English aliases for convenience.
_ALIASES = {
    "academic": "akademik",
    "daily": "gunluk",
    "edit": "duzenle",
    "workout": "antrenman",
    "note": "not",
    "help": "yardim",
    "günlük": "gunluk",
    "ödev": "odev",
    "yardım": "yardim",
    "tamamla": "complete",
    "delete": "sil",
    "reschedule": "ertele",
    "postpone": "ertele",
}


def parse_command(text: str) -> tuple[Optional[Command], str]:
    """Return (Command, remaining_text) if ``text`` starts with a known ``/cmd``.

    The command token is stripped; the remainder is what the node should act on.
    Unknown ``/words`` return ``(None, text)`` so the LLM router handles them.
    """
    stripped = text.lstrip()
    if not stripped.startswith("/"):
        return None, text
    head, _, rest = stripped[1:].partition(" ")
    key = head.strip().lower()
    key = _ALIASES.get(key, key)
    cmd = COMMANDS.get(key)
    if cmd is None:
        return None, text
    return cmd, rest.strip()


def help_text() -> str:
    """Human-readable list of all commands (used by /yardim and codes.md)."""
    lines = ["Kullanılabilir komutlar:"]
    for cmd in COMMANDS.values():
        lines.append(f"  /{cmd.name} — {cmd.description}")
    return "\n".join(lines)


__all__ = ["COMMANDS", "Command", "parse_command", "help_text"]
