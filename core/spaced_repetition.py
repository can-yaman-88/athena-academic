"""Spaced Repetition engine and LLM Analysis for Task Notes.

This module implements the SM-2 algorithm for spaced repetition, and an LLM-based
evaluator to score the user's recall quality based on task notes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from config import settings
from core.schemas import Task, TaskCategory

logger = logging.getLogger("athena.spaced_repetition")


class RecallScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recall_score: int = Field(ge=0, le=5, description="Score from 0 to 5.")
    score_reason: str = Field(description="Short, analytical justification.")
    future_warning: Optional[str] = Field(
        default=None, description="Warning for the next repetition if score < 4."
    )


ACADEMIC_MEMORY_EVALUATOR_PROMPT = """\
Sen katı ve analitik bir "Akademik Hafıza Değerlendiricisisin". Görevin, bir öğrencinin tamamladığı "Tekrar (Review)" görevi için yazdığı notları analiz ederek, konuyu ne kadar iyi hatırladığını değerlendirmek ve bir sonraki tekrar oturumu için zayıf noktaları tespit etmektir.

Sana görevin adı ve öğrencinin bu görev sırasındaki deneyimini anlattığı serbest metin notları verilecektir. 

Aşağıdaki metrikleri kesinlikle verilen kurallara göre belirle:

**1. Hatırlama Kalitesi Skoru (Recall Quality Score - 0 ile 5 arası tamsayı)**
Öğrencinin notundaki duygu durumuna, itiraflarına ve harcadığı efora bakarak aşağıdaki katı rubrik üzerinden puanla:

* **Skor 0 (Complete Blackout):** Öğrenci hiçbir şey hatırlamadığını, konunun aklından tamamen uçtuğunu belirtiyor.
* **Skor 1 (Vague Familiarity):** Konu aşina geliyor ancak detaylar, formüller veya kurallar tamamen yanlış hatırlanmış.
* **Skor 2 (Significant Struggle):** Hatırlamak için çok ciddi çaba/zaman harcanmış. Temel kurallar zar zor bir araya getirilmiş.
* **Skor 3 (Effortful Recall):** Temel kavramlar ve ana hatlar doğru hatırlandı, ancak öğrenci pürüzsüz hissetmiyor; ufak yardımlara ihtiyaç duymuş.
* **Skor 4 (Solid Recall):** Rahat ve duraksamasız bir hatırlama. Çok ufak ve önemsiz tereddütler dışında sorun yok.
* **Skor 5 (Effortless Perfection):** Kusursuz, zahmetsiz ve anında hatırlama. Konu tamamen zihne kazınmış.

*(Not: Eğer öğrenci sadece "Tamamlandı" gibi düz bir metin girmiş ve efordan bahsetmemişse, standart olarak 4 puan ver.)*

*Yalnızca hatırlama kanıtına bak: konuyla ilgisiz yorumları, ortam ya da motivasyon notlarını skora karıştırma. Skoru öğrencinin konuyu ne kadar hatırladığına göre ver; ne kadar süre çalıştığına değil.*

**2. Gelecek Oturum İçin Uyarı (Future Warning)**
Eğer verdiğin skor 4'ten küçükse, öğrencinin notlarında belirttiği spesifik zorlanma noktalarını tespit et. Bir sonraki tekrar görevi yaratıldığında öğrenciye gösterilmek üzere kısa, motive edici ve spesifik bir uyarı cümlesi yaz. Eğer skor 4 veya 5 ise bu alanı boş (null) bırak.

**Çıktı Formatı:** Sadece istenen alanları içeren yapılandırılmış bir veri dön.\
"""


def _default_llm(callbacks: Optional[list] = None) -> Any:
    from core.graph import _make_llm, _make_structured_llm

    llm = _make_llm(
        settings.notes_model, settings.notes_model_max_tokens, callbacks=callbacks
    )
    return _make_structured_llm(llm, RecallScore)


async def evaluate_recall(
    task_title: str, notes_text: str, *, llm: Any = None, callbacks: Optional[list] = None
) -> RecallScore:
    """Analyze a student's notes and evaluate recall quality.
    
    If the notes_text is completely empty or just whitespace, we solve it
    at the code level by assigning a default solid recall (Score 4) to save LLM cost.
    """
    if not notes_text or not notes_text.strip():
        return RecallScore(
            recall_score=4,
            score_reason="Boş not girildi, sistem otomatik olarak 4 (Solid Recall) puanı verdi.",
            future_warning=None,
        )

    if llm is None:
        llm = _default_llm(callbacks)

    content = f"Görev Adı: {task_title}\n\nÖğrenci Notları:\n{notes_text}"

    try:
        result: Optional[RecallScore] = await llm.ainvoke(
            [
                SystemMessage(content=ACADEMIC_MEMORY_EVALUATOR_PROMPT),
                HumanMessage(content=content),
            ]
        )
        return result or RecallScore(recall_score=4, score_reason="Fallback", future_warning=None)
    except Exception as exc:
        logger.exception("LLM recall evaluation failed")
        # Graceful fallback so the cycle doesn't break
        return RecallScore(
            recall_score=3,
            score_reason=f"LLM Analiz hatası: {exc}",
            future_warning="LLM analizi yapılamadı, sistem varsayılan döngüyle devam ediyor."
        )


def calculate_next_interval(
    score: int, consecutive_recalls: int, current_interval_days: int, ease_factor: float
) -> tuple[int, int, float]:
    """Calculate the next repetition parameters using the SM-2 algorithm.

    Returns:
        tuple[int, int, float]: (next_interval_days, consecutive_recalls, new_ease_factor)
    """
    # Calculate new ease factor
    # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    new_ease_factor = ease_factor + (0.1 - (5 - score) * (0.08 + (5 - score) * 0.02))
    new_ease_factor = max(1.3, new_ease_factor)

    if score < 3:
        # Failed recall
        return 1, 0, new_ease_factor
    else:
        # Successful recall
        new_recalls = consecutive_recalls + 1
        
        if new_recalls == 1:
            interval = 1
        elif new_recalls == 2:
            interval = 6
        else:
            interval = round(current_interval_days * new_ease_factor)
            
        return interval, new_recalls, new_ease_factor


async def handle_spaced_repetition_completion(
    completed_task: Task, db: Any, usage: Any = None, log_bus: Any = None
) -> None:
    """Orchestrates the spaced repetition flow when a task is completed.
    
    1. Checks if task is part of spaced repetition.
    2. Analyzes notes via LLM.
    3. Calculates next interval (SM-2).
    4. If recalls < 5, creates the next repetition task.
    """
    if not completed_task.is_spaced_repetition:
        return

    # Combine all notes for analysis
    all_notes = "\n".join(n.text for n in completed_task.notes)
    
    # 1. Evaluate Recall
    callbacks = []
    if usage:
        from core.usage_callback import AgentUsageCallback
        callbacks.append(AgentUsageCallback(usage))
        
    evaluation = await evaluate_recall(completed_task.title, all_notes, callbacks=callbacks)
    
    if log_bus:
        log_bus.emit(
            f"Spaced Repetition Analizi: Skor={evaluation.recall_score}, Neden={evaluation.score_reason}",
            level="info"
        )

    # 2. Calculate next parameters
    next_interval, new_recalls, new_ef = calculate_next_interval(
        score=evaluation.recall_score,
        consecutive_recalls=completed_task.streak,
        current_interval_days=completed_task.interval_days,
        ease_factor=completed_task.ease_factor,
    )

    # 3. Check for mastery (End cycle at 5 successful recalls)
    if new_recalls >= 5:
        if log_bus:
            log_bus.emit(f"Spaced Repetition Döngüsü Tamamlandı (Mezuniyet)! Görev: {completed_task.title}", level="info")
        return

    # 4. Create Next Task
    # The completed task may have no deadline (deadline is optional); fall back to
    # "now" so the repetition still gets scheduled instead of crashing.
    base_date = completed_task.deadline or datetime.now()
    next_date = base_date + timedelta(days=next_interval)
    
    from core.schemas import Note
    notes_to_add = []
    if evaluation.future_warning:
        notes_to_add.append(Note(text=f"🤖 Öğrenme Asistanı Notu: {evaluation.future_warning}"))
        
    # We strip "Tekrar: " from original task title if it already has it, to prevent "Tekrar: Tekrar: "
    base_title = completed_task.title
    if base_title.startswith("Tekrar: "):
        base_title = base_title.replace("Tekrar: ", "", 1).strip()
        
    next_task = Task(
        title=f"Tekrar: {base_title}",
        deadline=next_date,
        discipline=completed_task.discipline,
        estimated_hours=completed_task.estimated_hours,
        category=TaskCategory.ACADEMIC,
        subtype=completed_task.subtype,
        parent_id=completed_task.parent_id,
        is_spaced_repetition=True,
        streak=new_recalls,
        ease_factor=new_ef,
        interval_days=next_interval,
        original_task_id=completed_task.original_task_id or completed_task.id,
        notes=notes_to_add,
        materials=completed_task.materials, # inherit materials
        tags=completed_task.tags, # inherit tags
    )
    
    await db.create_task(next_task)
    
    if log_bus:
        log_bus.emit(
            f"Yeni Tekrar Görevi Oluşturuldu: {next_task.title} ({next_interval} gün sonra, EF: {new_ef:.2f})",
            level="info"
        )
