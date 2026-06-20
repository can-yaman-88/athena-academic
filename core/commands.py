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
    "gorev": Command(
        "gorev", "task_tool_node",
        "Günlük görev ekler. Mesajdaki ekstra detaylar görevin notlarına kaydedilir.",
        {"operation": "create", "category": "daily", "generate_subtasks": False},
    ),
    "agorev": Command(
        "agorev", "task_tool_node",
        "Akademik görev ekler. Alt görev parçalaması yapılmaz.",
        {"operation": "create", "category": "academic", "generate_subtasks": False},
    ),
    "altgorev": Command(
        "altgorev", "task_tool_node",
        "Günlük görev ekler ve verilen sayı kadar alt göreve böler.",
        {"operation": "create", "category": "daily", "generate_subtasks": True},
    ),
    "altakademik": Command(
        "altakademik", "task_tool_node",
        "Akademik görev ekler ve verilen sayı kadar alt göreve böler.",
        {"operation": "create", "category": "academic", "generate_subtasks": True},
    ),
    "fikir": Command(
        "fikir", "idea_extractor_node",
        "Girdi içinden parantez içindeki değer kadar fikir üretir.",
        {"operation": "extract_ideas"},
    ),
    "antrenman": Command(
        "antrenman", "workout_tool_node",
        "Tek bir planlı antrenman ekler. Yorumlar notlar kısmına eklenir.",
        {"mode": "single", "status": "planned"},
    ),
    "seans": Command(
        "seans", "session_node",
        "Akademik görevin altına bir seans ekler.",
        {"operation": "create_session"},
    ),
    "plan": Command(
        "plan", "task_tool_node",
        "Akademik bir hedef için plan girdisinden görevler/alt görevler oluşturur.",
        {"operation": "create_plan", "category": "academic", "generate_subtasks": True},
    ),
    "aralik": Command(
        "aralik", "task_tool_node",
        "Aralıklı görev oluşturur. Alt görevler de aralıklı olur.",
        {"operation": "create", "category": "academic", "is_spaced_repetition": True, "generate_subtasks": True},
    ),
    "yardim": Command(
        "yardim", "chat_node",
        "Komut listesini göster.",
        {"mode": "help"},
    ),
}

# A few English aliases for convenience.
_ALIASES = {
    "agörev": "agorev",
    "altgörev": "altgorev",
    "altakademik": "altakademik",
    "görev": "gorev",
    "aralık": "aralik",
    "yardım": "yardim",
}


import re

def parse_command(text: str) -> tuple[Optional[Command], str, Optional[int]]:
    """Return (Command, remaining_text, N) if ``text`` contains known ``/cmd``s.

    The command tokens are stripped. If multiple commands are found, the first one 
    dictates the route, but their hints are merged.
    """
    pattern = r"(?:^|\s)/([a-zA-ZğüşıöçĞÜŞİÖÇ]+)(?:\((\d+)\))?(?:\s|$)"
    matches = list(re.finditer(pattern, text))
    
    primary_cmd = None
    merged_hints = {}
    n_val = None
    
    # Strip tokens from right to left to preserve indices
    rest = text
    for m in reversed(matches):
        key = m.group(1).lower()
        key = _ALIASES.get(key, key)
        if COMMANDS.get(key) is not None:
            # Carefully remove the token
            start = m.start()
            end = m.end()
            if text[start:end].startswith(" "):
                rest = rest[:start] + " " + rest[end:]
            else:
                rest = rest[:start] + rest[end:]

    # Left to right to find primary command and merge hints
    for m in matches:
        key = m.group(1).lower()
        key = _ALIASES.get(key, key)
        cmd = COMMANDS.get(key)
        if cmd is not None:
            if primary_cmd is None:
                primary_cmd = cmd
            
            # Merge hints. Later commands overwrite conflicting hints of earlier ones,
            # or we can just update dict.
            merged_hints.update(cmd.hints)
            
            if m.group(2) and n_val is None:
                try:
                    n_val = int(m.group(2))
                except ValueError:
                    pass

    if primary_cmd is not None:
        from dataclasses import replace
        final_cmd = replace(primary_cmd, hints=merged_hints)
        return final_cmd, rest.strip(), n_val
        
    return None, text, None


def help_text() -> str:
    """Human-readable list of all commands (used by /yardim and codes.md)."""
    lines = ["Kullanılabilir komutlar:"]
    for cmd in COMMANDS.values():
        lines.append(f"  /{cmd.name} — {cmd.description}")
    return "\n".join(lines)


__all__ = ["COMMANDS", "Command", "parse_command", "help_text"]
