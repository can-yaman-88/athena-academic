"""LaTeX cleaning, deterministic repair, engine selection and async compilation.

Vendored verbatim (logic-wise) from the upstream ``services/latex_engine.py``;
only the logger and config type are swapped for Athena-Academic's. Compilation
flow per document:
  1. clean_latex  -> strip markdown fences, crop to documentclass..end{document}.
  2. deterministic fix_latex (free, fast) -> close known pitfalls.
  3. compile. On failure: re-apply deterministic fix, else LLM self-correction
     (max N attempts), breaking the loop if it converges on the same source.
The temp directory is always managed via ``tempfile.TemporaryDirectory``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from .engine_config import EngineConfig

log = logging.getLogger("athena.pdf_engine.latex")

# (code, error_log) -> corrected code  (LLM self-correction callback)
Corrector = Callable[[str, str], Awaitable[str]]


@dataclass
class CompileResult:
    success: bool
    pdf_path: Optional[Path]
    tex_path: Optional[Path]
    final_source: str
    attempts: int
    error_tail: str = ""


def clean_latex(content: str) -> str:
    content = re.sub(r"^```(?:latex|tex)?\s*\n?", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n?```\s*$", "", content, flags=re.MULTILINE)
    content = content.strip()

    m = re.search(r"\\documentclass", content)
    if m:
        content = content[m.start():]
    m = re.search(r"\\end\{document\}", content)
    if m:
        content = content[: m.end()]
    elif "\\documentclass" in content:
        content += "\n\\end{document}\n"
    return content


def strip_emoji(content: str) -> str:
    """Remove emoji/high-unicode that breaks pdflatex (mainly in exams)."""
    for e in ["💡", "⚠️", "⚠", "📝", "📌", "✅", "❌", "🔑", "⭐", "🎯", "✏️", "✏", "🔍"]:
        content = content.replace(e, "")
    return "".join(c for c in content if ord(c) < 0x2700 or ord(c) < 128)


def fix_latex(content: str) -> str:
    """Deterministically (for free) fix common compile errors."""
    fixed = content

    envs = {
        "definition": "Definition",
        "theorem": "Theorem",
        "lemma": "Lemma",
        "corollary": "Corollary",
        "proposition": "Proposition",
        "example": "Example",
        "remark": "Remark",
    }
    for env, label in envs.items():
        if f"\\begin{{{env}}}" in fixed and f"\\newtheorem{{{env}}}" not in fixed:
            fixed = fixed.replace(
                "\\begin{document}",
                f"\\newtheorem{{{env}}}{{{label}}}[section]\n\\begin{{document}}",
            )

    boxes = {
        "hintbox": ("blue!5!white", "blue!60!black", "Hint"),
        "warningbox": ("red!5!white", "red!70!black", "Warning"),
        "notebox": ("green!5!white", "green!50!black", "Note"),
    }
    for box, (bg, frame, title) in boxes.items():
        if f"\\begin{{{box}}}" in fixed and f"\\newtcolorbox{{{box}}}" not in fixed:
            defn = (
                f"\\newtcolorbox{{{box}}}[1]{{colback={bg},colframe={frame},"
                f"fonttitle=\\bfseries,title={{{title}: #1}},"
                f"sharp corners,boxrule=0.8pt,left=6pt,right=6pt,top=4pt,bottom=4pt}}\n"
            )
            fixed = fixed.replace("\\begin{document}", defn + "\\begin{document}")

    if "hintbox" in fixed or "warningbox" in fixed or "notebox" in fixed:
        if "\\usepackage" in fixed and "tcolorbox" not in fixed:
            fixed = fixed.replace(
                "\\begin{document}",
                "\\usepackage[most]{tcolorbox}\n\\begin{document}",
            )

    if "pgfplots" in fixed and "\\pgfplotsset{compat" not in fixed:
        fixed = fixed.replace(
            "\\usepackage{pgfplots}",
            "\\usepackage{pgfplots}\n\\pgfplotsset{compat=1.18}",
        )

    if "shape=origin" in fixed:
        fixed = fixed.replace("shape=origin", "")
    if re.search(r"\(origin\)", fixed) and not re.search(
        r"\\coordinate\s*\(origin\)", fixed
    ):
        fixed = re.sub(
            r"(\\begin\{tikzpicture\}(\[.*?\])?)",
            r"\1\n  \\coordinate (origin) at (0,0);",
            fixed,
        )

    fixed = re.sub(r",\s*,", ",", fixed)
    fixed = re.sub(r"\[\s*,", "[", fixed)
    fixed = re.sub(r",\s*\]", "]", fixed)
    return fixed


class LatexEngine:
    def __init__(self, cfg: EngineConfig) -> None:
        self.cfg = cfg
        self._engine: str | None = None

    async def detect_engine(self) -> str:
        if self._engine:
            return self._engine
        for engine in self.cfg.latex["engines"]:
            if shutil.which(engine):
                self._engine = engine
                return engine
        self._engine = "pdflatex"
        return self._engine

    @staticmethod
    def _adapt_for_unicode_engine(content: str) -> str:
        content = re.sub(r"\\usepackage\[utf8\]\{inputenc\}", "", content)
        content = re.sub(r"\\usepackage\[T1\]\{fontenc\}", "", content)
        if "\\usepackage{fontspec}" not in content:
            content = content.replace(
                "\\begin{document}", "\\usepackage{fontspec}\n\\begin{document}"
            )
        return content

    async def _run_engine(
        self, engine: str, tex_file: Path, work_dir: Path, halt: bool
    ) -> tuple[int, str]:
        args = [
            engine,
            "-interaction=nonstopmode",
            "-output-directory",
            str(work_dir),
            str(tex_file),
        ]
        if halt:
            args.insert(1, "-halt-on-error")
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=self.cfg.latex["compile_timeout"]
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                log.error("%s timed out", engine)
                return 1, "TIMEOUT"
            return proc.returncode, stdout.decode("utf-8", "ignore")
        except FileNotFoundError:
            return 1, f"{engine} not found"

    @staticmethod
    def _extract_errors(compiler_output: str) -> str:
        lines = [
            ln
            for ln in compiler_output.splitlines()
            if ln.startswith("!") or "Fatal" in ln or "Error" in ln
        ]
        return "\n".join(lines[:30])

    async def compile(
        self,
        content: str,
        *,
        output_dir: Path,
        output_name: str,
        kind: str,  # "notes" | "exam"
        save_tex: bool = True,
        corrector: Corrector | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> CompileResult:
        """Compile LaTeX, applying deterministic + LLM self-correction as needed."""

        def _progress(msg: str) -> None:
            if on_progress is not None:
                try:
                    on_progress(msg)
                except Exception:  # progress reporting must never break compilation
                    pass

        output_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.temp_folder.mkdir(parents=True, exist_ok=True)
        engine = await self.detect_engine()
        log.info("LaTeX engine: %s", engine)

        content = clean_latex(content)
        if kind == "exam":
            content = strip_emoji(content)

        tex_out = output_dir / f"{output_name}.tex"
        if not content or "\\documentclass" not in content:
            log.error("no valid LaTeX content")
            if content and save_tex:
                tex_out.write_text(content, encoding="utf-8")
            return CompileResult(
                False,
                None,
                tex_out if content else None,
                content,
                0,
                "no \\documentclass",
            )

        if engine in ("lualatex", "xelatex"):
            content = self._adapt_for_unicode_engine(content)

        # first deterministic repair (free)
        content = fix_latex(content)
        if save_tex:
            tex_out.write_text(content, encoding="utf-8")

        max_attempts = max(1, int(self.cfg.latex["self_correction_attempts"]))
        seen_hashes: set[int] = set()
        current = content
        last_errors = ""

        with tempfile.TemporaryDirectory(
            prefix=f"{kind}_compile_", dir=str(self.cfg.temp_folder)
        ) as tmp:
            work = Path(tmp)
            tex_file = work / "document.tex"

            for attempt in range(1, max_attempts + 1):
                log.info("[%s] compile attempt %d/%d", output_name, attempt, max_attempts)
                _progress(f"compile {attempt}/{max_attempts}")
                tex_file.write_text(current, encoding="utf-8")
                for f in work.glob("document.*"):
                    if f.suffix != ".tex":
                        f.unlink(missing_ok=True)

                errors = ""
                for run in range(1, int(self.cfg.latex["passes"]) + 1):
                    rc, out = await self._run_engine(
                        engine,
                        tex_file,
                        work,
                        halt=(run == self.cfg.latex["passes"]),
                    )
                    if rc != 0 and run == self.cfg.latex["passes"]:
                        errors = self._extract_errors(out)

                produced = work / "document.pdf"
                if produced.exists() and produced.stat().st_size > 0:
                    pdf_out = output_dir / f"{output_name}.pdf"
                    shutil.copy2(produced, pdf_out)
                    if save_tex:
                        tex_out.write_text(current, encoding="utf-8")
                    log.info(
                        "[%s] PDF produced (%.1f KB)",
                        output_name,
                        pdf_out.stat().st_size / 1024,
                    )
                    return CompileResult(True, pdf_out, tex_out, current, attempt)

                last_errors = errors or last_errors
                for ln in errors.splitlines()[:3]:
                    log.warning("    %s", ln.strip())

                if attempt >= max_attempts:
                    break

                # 1) deterministic fix
                deterministic = fix_latex(current)
                if deterministic != current:
                    log.info("applied deterministic fix")
                    current = deterministic
                    continue

                # 2) LLM self-correction (loop guard: converge on same source)
                h = hash(current)
                if corrector is None or h in seen_hashes:
                    log.warning("self-correction converged/absent; stopping")
                    break
                seen_hashes.add(h)
                log.info("trying LLM self-correction...")
                _progress(f"AI fix (attempt {attempt + 1}/{max_attempts})")
                corrected = await corrector(current, last_errors)
                if not corrected or corrected.strip() == current.strip():
                    log.warning("self-correction produced no change; stopping")
                    break
                current = clean_latex(corrected)
                if engine in ("lualatex", "xelatex"):
                    current = self._adapt_for_unicode_engine(current)

        if save_tex:
            tex_out.write_text(current, encoding="utf-8")
        log.error("[%s] could not produce PDF; .tex saved: %s", output_name, tex_out)
        return CompileResult(False, None, tex_out, current, max_attempts, last_errors)


__all__ = ["CompileResult", "LatexEngine", "clean_latex", "fix_latex", "strip_emoji"]
