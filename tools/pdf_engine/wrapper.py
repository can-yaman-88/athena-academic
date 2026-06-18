"""In-process PDF -> LaTeX pipeline with ChromaDB ingestion and job tracking.

``process_academic_pdf`` drives the vendored engine end to end for a single PDF:
extract text (or fall back to page images), transcribe to LaTeX lecture notes,
compile them, ingest the notes into ChromaDB so the agent can retrieve them, and
(full pipeline) generate an exam PDF and Anki flashcards. Progress and failures
are logged through the ``athena.pdf_engine`` namespace so they surface in the
live log stream, and a :class:`~core.schemas.PdfJob` row is kept up to date for
the dashboard's "past PDFs" panel.

Everything blocking (PDF parsing, file IO, LaTeX subprocess, the sync ChromaDB
API) is kept off the event-loop thread; the OpenRouter calls are natively async.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict, Field

from config import settings
from core.schemas import PdfJob, PdfJobStatus
from tools.pdf_engine.automation import (
    AIClient,
    LatexEngine,
    build_engine_config,
    generate_flashcards_from_notes,
)

logger = logging.getLogger("athena.pdf_engine")


class PdfJobResult(BaseModel):
    """Validated outcome of a PDF job, shaped for the LangGraph state / API."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    job_id: str
    status: PdfJobStatus
    filename: str
    artifacts: list[str] = Field(default_factory=list)
    notes_pdf: Optional[str] = None
    chunks_ingested: int = 0
    cost_usd: float = 0.0
    summary: str = ""


# --------------------------------------------------------------------------- #
# PDF -> text/markdown extraction (digital vs scanned routing)
# --------------------------------------------------------------------------- #
def _extract_markdown(pdf_path: Path) -> tuple[str, int]:
    """Extract the PDF text layer as markdown -> (markdown, page_count)."""
    import pymupdf  # ships with pymupdf4llm
    import pymupdf4llm

    with pymupdf.open(str(pdf_path)) as doc:
        pages = doc.page_count
    md = pymupdf4llm.to_markdown(str(pdf_path), show_progress=False)
    return md, pages


def _convert_to_images(pdf_path: Path) -> list:
    from pdf2image import convert_from_path

    return convert_from_path(
        str(pdf_path), dpi=settings.pdf_dpi, fmt=settings.pdf_image_format
    )


async def _try_text_transcribe(ai: AIClient, pdf_path: Path, name: str) -> Optional[str]:
    """Transcribe via the text layer when it's rich enough, else None (-> images)."""
    if not settings.pdf_prefer_text:
        return None
    try:
        markdown, pages = await asyncio.to_thread(_extract_markdown, pdf_path)
    except Exception as exc:  # noqa: BLE001 - extraction failure must never block
        logger.info("%s: text extraction failed (%s); using image path", name, type(exc).__name__)
        return None

    chars = len("".join(markdown.split()))
    threshold = settings.pdf_min_chars_per_page
    if pages == 0 or chars / pages < threshold:
        logger.info(
            "%s: text layer too thin (~%d chars/page < %d); using image path",
            name,
            chars // max(pages, 1),
            threshold,
        )
        return None

    logger.info("%s: text layer found (%d pages) -> markdown transcription", name, pages)
    # Stash the markdown so the caller can ingest the cleaner text into ChromaDB.
    _try_text_transcribe.last_markdown = markdown  # type: ignore[attr-defined]
    return await ai.transcribe_text(markdown, name)


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
async def process_academic_pdf(
    file_path: str,
    user_instructions: str = "",
    *,
    chroma_manager: Any = None,
    usage_tracker: Any = None,
    log_bus: Any = None,  # accepted for symmetry; logging flows via the handler
    sqlite_manager: Any = None,
    job_id: Optional[str] = None,
    ai_client: Any = None,
) -> PdfJobResult:
    """Run a PDF through the in-process engine; ingest notes; track the job."""
    pdf_path = Path(file_path)
    name = pdf_path.name
    stem = pdf_path.stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    cfg = build_engine_config()
    cfg.ensure_dirs()

    # Track this job's spend by diffing the usage tracker around the run.
    def _pdf_cost() -> float:
        if usage_tracker is None:
            return 0.0
        try:
            return float(usage_tracker.snapshot().get("pdf", {}).get("total_cost_usd", 0.0))
        except Exception:  # noqa: BLE001
            return 0.0

    cost_before = _pdf_cost()

    job = PdfJob(filename=name, status=PdfJobStatus.PROCESSING)
    if job_id:
        job.id = job_id
    if sqlite_manager is not None:
        try:
            await sqlite_manager.create_pdf_job(job)
        except Exception:  # noqa: BLE001 - job tracking must not abort processing
            logger.exception("could not persist initial PDF job row")

    async def _finalize(
        *,
        success: bool,
        status: PdfJobStatus,
        artifacts: list[str],
        notes_pdf: Optional[str],
        chunks: int,
        summary: str,
        error: Optional[str] = None,
    ) -> PdfJobResult:
        cost = round(max(0.0, _pdf_cost() - cost_before), 6)
        job.status = status
        job.completed_at = datetime.now()
        job.artifacts = artifacts
        job.cost_usd = cost
        job.chunks_ingested = chunks
        job.error = error
        job.summary = summary
        if sqlite_manager is not None:
            try:
                await sqlite_manager.update_pdf_job(job)
            except Exception:  # noqa: BLE001
                logger.exception("could not update PDF job row")
        logger.info("[%s] %s — %s", name, status.value, summary)
        return PdfJobResult(
            success=success,
            job_id=job.id,
            status=status,
            filename=name,
            artifacts=artifacts,
            notes_pdf=notes_pdf,
            chunks_ingested=chunks,
            cost_usd=cost,
            summary=summary,
        )

    if not pdf_path.exists():
        return await _finalize(
            success=False,
            status=PdfJobStatus.FAILED,
            artifacts=[],
            notes_pdf=None,
            chunks=0,
            summary=f"File not found: {file_path}",
            error="file_not_found",
        )

    logger.info("processing PDF: %s", name)

    # The AIClient is an async context manager; tests can inject a ready fake.
    owns_client = ai_client is None
    if owns_client:
        usage = usage_tracker
        if usage is None:
            from tools.pdf_engine.automation import UsageTracker

            usage = UsageTracker(
                pricing=settings.model_pricing,
                default_pricing=settings.default_model_pricing,
            )
        ai_cm = AIClient(cfg, usage)
    else:
        ai_cm = None

    try:
        if owns_client:
            ai = await ai_cm.__aenter__()
        else:
            ai = ai_client

        engine = LatexEngine(cfg)
        _try_text_transcribe.last_markdown = None  # type: ignore[attr-defined]

        # 1) transcription (text-first; image fallback)
        latex = await _try_text_transcribe(ai, pdf_path, name)
        if latex is None:
            images = await asyncio.to_thread(_convert_to_images, pdf_path)
            if not images:
                raise RuntimeError("could not convert PDF to images")
            logger.info("%s: %d page(s) rasterized", name, len(images))
            latex = await ai.transcribe_images(images, name)

        if not latex or not latex.strip():
            return await _finalize(
                success=False,
                status=PdfJobStatus.FAILED,
                artifacts=[],
                notes_pdf=None,
                chunks=0,
                summary="The model returned empty LaTeX.",
                error="empty_transcription",
            )

        logger.info("%s: transcription complete (%d chars LaTeX)", name, len(latex))

        # 2) optional pre-compile validation
        if settings.pdf_validate_before_compile:
            logger.info("%s: validating LaTeX before compile", name)
            latex = await ai.validate_latex(latex, kind="notes")

        # 3) compile notes (deterministic + LLM self-correction inside)
        logger.info("%s: compiling notes PDF", name)
        notes_name = f"{stem}_{ts}"
        notes_result = await engine.compile(
            latex,
            output_dir=cfg.output_folder,
            output_name=notes_name,
            kind="notes",
            corrector=lambda code, err: ai.correct_latex(code, err, "notes"),
        )
        notes_latex = notes_result.final_source or latex

        artifacts: list[str] = []
        if notes_result.tex_path:
            artifacts.append(str(notes_result.tex_path))
        notes_pdf = str(notes_result.pdf_path) if notes_result.pdf_path else None
        if notes_pdf:
            artifacts.append(notes_pdf)

        # 4) ingest notes into ChromaDB (prefer the cleaner extracted markdown)
        chunks = 0
        ingest_text = getattr(_try_text_transcribe, "last_markdown", None) or notes_latex
        if chroma_manager is not None and ingest_text.strip():
            metadata = {
                "source": name,
                "job_id": job.id,
                "artifact_type": "notes",
                "user_instructions": user_instructions,
            }
            try:
                chunk_ids = await asyncio.to_thread(
                    chroma_manager.add_document, ingest_text, metadata
                )
                chunks = len(chunk_ids)
                logger.info("%s: ingested %d chunk(s) into knowledge base", name, chunks)
            except Exception:  # noqa: BLE001 - ingestion failure shouldn't fail the job
                logger.exception("%s: ChromaDB ingestion failed", name)

        # 5) (full pipeline) exam + flashcards from the notes — best effort
        if settings.pdf_generate_exam:
            try:
                logger.info("%s: generating exam", name)
                notes_for_exam = notes_latex[: settings.pdf_exam_notes_max_chars]
                exam_latex = await ai.generate_exam(notes_for_exam, name)
                if exam_latex.strip():
                    if settings.pdf_validate_before_compile:
                        exam_latex = await ai.validate_latex(exam_latex, kind="exam")
                    exam_result = await engine.compile(
                        exam_latex,
                        output_dir=cfg.exam_folder,
                        output_name=f"EXAM_{stem}_{ts}",
                        kind="exam",
                        save_tex=False,
                        corrector=lambda code, err: ai.correct_latex(code, err, "exam"),
                    )
                    if exam_result.pdf_path:
                        artifacts.append(str(exam_result.pdf_path))
            except Exception:  # noqa: BLE001 - exam failure must not fail the notes
                logger.exception("%s: exam generation failed", name)

        if settings.pdf_generate_flashcards:
            try:
                logger.info("%s: generating flashcards", name)
                notes_for_cards = notes_latex[: settings.pdf_exam_notes_max_chars]
                _, card_paths = await generate_flashcards_from_notes(
                    ai=ai,
                    cfg=cfg,
                    notes=notes_for_cards,
                    source_name=name,
                    output_name=f"CARDS_{stem}_{ts}",
                )
                artifacts.extend(str(p) for p in card_paths)
            except Exception:  # noqa: BLE001 - flashcard failure must not fail the notes
                logger.exception("%s: flashcard generation failed", name)

        if notes_result.success:
            summary = (
                f"Processed '{name}': notes compiled, {chunks} chunk(s) ingested, "
                f"{len(artifacts)} artifact(s) produced."
            )
            return await _finalize(
                success=True,
                status=PdfJobStatus.COMPLETED,
                artifacts=artifacts,
                notes_pdf=notes_pdf,
                chunks=chunks,
                summary=summary,
            )
        # Notes didn't compile but we still have .tex + ingested text.
        summary = (
            f"Processed '{name}': notes did NOT compile (.tex saved), "
            f"{chunks} chunk(s) ingested."
        )
        return await _finalize(
            success=bool(chunks) or bool(artifacts),
            status=PdfJobStatus.COMPLETED if chunks else PdfJobStatus.FAILED,
            artifacts=artifacts,
            notes_pdf=None,
            chunks=chunks,
            summary=summary,
            error=None if chunks else (notes_result.error_tail or "compile_failed"),
        )

    except Exception as exc:  # noqa: BLE001 - never crash a fire-and-forget task
        logger.exception("PDF processing crashed for %s", name)
        return await _finalize(
            success=False,
            status=PdfJobStatus.FAILED,
            artifacts=[],
            notes_pdf=None,
            chunks=0,
            summary=f"PDF processing failed: {exc}",
            error=str(exc),
        )
    finally:
        if owns_client and ai_cm is not None:
            await ai_cm.__aexit__(None, None, None)


def result_to_state_update(result: PdfJobResult) -> dict[str, Any]:
    """Map a :class:`PdfJobResult` to a LangGraph state partial."""
    return {
        "messages": [AIMessage(content=result.summary)],
        "active_tool": "process_academic_pdf",
    }


__all__ = ["PdfJobResult", "process_academic_pdf", "result_to_state_update"]
