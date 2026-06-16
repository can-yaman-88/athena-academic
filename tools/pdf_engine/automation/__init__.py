"""In-process PDF->LaTeX automation engine (vendored, sync/watch/TUI removed).

Adapted from github.com/can-yaman-88/PDF-OCR-MD-LaTeX-PDF-Lecture-Automation:
the OCR/transcription, LaTeX compilation, validation and flashcard generation
engine is kept, while the rclone sync, watchdog file-watcher and rich TUI are
dropped. Everything runs in-process and is driven by
:func:`tools.pdf_engine.wrapper.process_academic_pdf`.
"""

from .ai_client import AIClient
from .engine_config import EngineConfig, build_engine_config
from .flashcard import generate_flashcards_from_notes
from .latex_engine import CompileResult, LatexEngine
from .usage import UsageTracker

__all__ = [
    "AIClient",
    "CompileResult",
    "EngineConfig",
    "LatexEngine",
    "UsageTracker",
    "build_engine_config",
    "generate_flashcards_from_notes",
]
