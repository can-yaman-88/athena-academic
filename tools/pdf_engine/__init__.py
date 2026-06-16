"""PDF->LaTeX engine integration for Athena-Academic.

Exposes the async wrapper that runs the vendored in-process OCR/MD->LaTeX->PDF
engine (notes + exam + Anki flashcards), ingests the notes into ChromaDB, and
tracks each run as a :class:`~core.schemas.PdfJob`. The engine itself lives in
:mod:`tools.pdf_engine.automation`.
"""

from tools.pdf_engine.wrapper import (
    PdfJobResult,
    process_academic_pdf,
    result_to_state_update,
)

__all__ = [
    "PdfJobResult",
    "process_academic_pdf",
    "result_to_state_update",
]
