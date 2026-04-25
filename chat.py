"""
Chat orchestrator: scene question-answer.
Single-turn, offline (Ollama + Gemma 3 1B).

API:
  answer_query(question, frame, detections, lang) -> str
"""
from __future__ import annotations

_OLLAMA_MODEL = "gemma3:1b"

_SYSTEM = {
    "zh": (
        "你是視障導航助理。根據偵測到的物件與文字，"
        "用繁體中文簡短回答（50字以內）。資訊不足時回「無法判斷」。"
    ),
    "en": (
        "You are a blind navigation assistant. Answer briefly in English "
        "(under 50 words) based on detected objects and text in the scene. "
        "If info is insufficient, say 'cannot determine'."
    ),
    "ja": (
        "視覚障害者向けナビゲーションアシスタント。"
        "50字以内の日本語で簡潔に答えてください。情報不足なら「判断できません」。"
    ),
}

_NO_DETECT = {
    "zh": "（無偵測結果）",
    "en": "(no detections)",
    "ja": "（検出なし）",
}


def _build_context(detections: list, ocr_results: list, lang: str) -> str:
    parts = []
    if detections:
        labels = list(dict.fromkeys(d[0] for d in detections[:5]))
        dist_map = {d[0]: d[1] for d in detections[:5]}
        if lang == "zh":
            parts.append("偵測物件：" + "、".join(f"{lb}（{dist_map[lb]}）" for lb in labels))
        elif lang == "en":
            parts.append("Objects: " + ", ".join(f"{lb} ({dist_map[lb]})" for lb in labels))
        else:
            parts.append("検出：" + "、".join(f"{lb}（{dist_map[lb]}）" for lb in labels))

    if ocr_results:
        texts = [r[1] for r in ocr_results[:8] if r[1].strip()]
        if texts:
            if lang == "zh":
                parts.append("畫面文字：" + "、".join(f"「{t}」" for t in texts))
            elif lang == "en":
                parts.append("Text: " + ", ".join(f'"{t}"' for t in texts))
            else:
                parts.append("テキスト：" + "、".join(f"「{t}」" for t in texts))

    return "\n".join(parts) if parts else _NO_DETECT.get(lang, _NO_DETECT["zh"])


def _trim_to_sentence(text: str, max_chars: int = 80) -> str:
    for sep in ("。", "！", "？", ".", "!", "?", "\n"):
        idx = text.find(sep)
        if 0 < idx < max_chars:
            return text[: idx + 1]
    return text[:max_chars]


def answer_query(
    question: str,
    frame,            # numpy BGR
    detections: list,
    lang: str = "zh",
) -> str:
    """Scene Q&A: OCR frame + YOLO context → Ollama → answer string.
    Returns '' if question is empty or Ollama fails.
    """
    if not question.strip():
        return ""

    import omni_sense_ocr

    ocr_results = omni_sense_ocr.ocr_full_frame(frame)
    context = _build_context(detections, ocr_results, lang)
    system = _SYSTEM.get(lang, _SYSTEM["zh"])

    try:
        import ollama

        resp = ollama.chat(
            model=_OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"場景：\n{context}\n\n問題：{question}",
                },
            ],
            options={"num_predict": 80, "temperature": 0.2},
            stream=False,
        )
        raw = resp["message"]["content"].strip()
        return _trim_to_sentence(raw)
    except Exception:
        return ""
