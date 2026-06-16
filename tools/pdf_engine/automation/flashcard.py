"""Generate Anki flashcards (CSV + optional .apkg) from LaTeX lecture notes.

Vendored from the upstream ``generator/flashcard.py``; only the logger and config
type are adapted. Flow: ask the model for a JSON card array, parse it robustly,
always write a CSV (Anki "Import File"), and additionally write an ``.apkg`` if
``genanki`` is installed. No step blocks the pipeline; on error, card generation
is skipped and the notes/exam flow is unaffected.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .ai_client import AIClient
from .engine_config import EngineConfig

log = logging.getLogger("athena.pdf_engine.flashcard")

try:
    import genanki  # type: ignore

    _HAS_GENANKI = True
except ImportError:
    _HAS_GENANKI = False


@dataclass
class Flashcard:
    front: str
    back: str
    tags: list[str] = field(default_factory=list)


def _parse_cards(raw: str) -> list[Flashcard]:
    """Parse a JSON card array from the model output as robustly as possible."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start: end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("could not parse flashcard JSON: %s", exc)
        return []

    cards: list[Flashcard] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        front = str(item.get("front", "")).strip()
        back = str(item.get("back", "")).strip()
        if not front or not back:
            continue
        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        tags = [re.sub(r"\s+", "_", str(t).strip()) for t in tags if str(t).strip()]
        cards.append(Flashcard(front=front, back=back, tags=tags))
    return cards


def _write_csv(cards: list[Flashcard], path: Path) -> None:
    # Anki CSV: front; back; tags (space-separated). Semicolon delimiter.
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(["#separator:Semicolon"])
        writer.writerow(["#html:true"])
        writer.writerow(["#tags column:3"])
        for c in cards:
            writer.writerow([c.front, c.back, " ".join(c.tags)])


def _write_apkg(cards: list[Flashcard], path: Path, deck_name: str) -> bool:
    if not _HAS_GENANKI:
        return False
    try:
        model = genanki.Model(
            1607392319,
            "Athena Basic",
            fields=[{"name": "Front"}, {"name": "Back"}],
            templates=[
                {
                    "name": "Card 1",
                    "qfmt": "{{Front}}",
                    "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
                }
            ],
        )
        deck = genanki.Deck(abs(hash(deck_name)) % (10**10), deck_name)
        for c in cards:
            deck.add_note(
                genanki.Note(model=model, fields=[c.front, c.back], tags=c.tags)
            )
        genanki.Package(deck).write_to_file(str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("could not write .apkg: %s", exc)
        return False


async def generate_flashcards_from_notes(
    *,
    ai: AIClient,
    cfg: EngineConfig,
    notes: str,
    source_name: str,
    output_name: str,
) -> tuple[int, list[Path]]:
    """Generate cards, write files, return (card_count, written_paths)."""
    raw = await ai.generate_flashcards(notes, source_name)
    cards = _parse_cards(raw)
    if not cards:
        log.warning("[%s] no flashcards generated", source_name)
        return 0, []

    cfg.flashcard_folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    csv_path = cfg.flashcard_folder / f"{output_name}.csv"
    _write_csv(cards, csv_path)
    written.append(csv_path)
    log.info("[%s] %d flashcards -> %s", source_name, len(cards), csv_path.name)

    apkg_path = cfg.flashcard_folder / f"{output_name}.apkg"
    if _write_apkg(cards, apkg_path, deck_name=output_name):
        written.append(apkg_path)
        log.info("[%s] Anki package -> %s", source_name, apkg_path.name)
    elif not _HAS_GENANKI:
        log.info("genanki not installed; produced CSV only (pip install genanki)")

    return len(cards), written


__all__ = ["Flashcard", "generate_flashcards_from_notes"]
