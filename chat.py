"""
Chat orchestrator: scene question-answer.
Single-turn, offline (Ollama + Gemma 3 1B).

API:
  answer_query(question, frame, detections, lang) -> str
"""
from __future__ import annotations
import re

_OLLAMA_MODEL = "gemma3:1b"

# Regex: filter OCR results that look like timestamps / date strings (video watermarks etc.)
_TIMESTAMP_RE = re.compile(
    r"^\d{4}[/\-]\d|\d{4}/\d{2}/\d{2}|^\d{2}:\d{2}:\d{2}"
)

_SYSTEM = {
    "zh": (
        "你是視障導航助理。根據偵測到的物件與文字直接回答，"
        "用繁體中文一句話（30字以內）。不要說「我」、不要道歉、不要重複問題。"
    ),
    "en": (
        "You are a blind navigation assistant. Give a direct one-sentence answer "
        "(under 30 words) based on the detected objects and text. "
        "No apologies, no repeating the question."
    ),
    "ja": (
        "視覚障害者向けナビゲーションアシスタント。"
        "検出情報を元に30字以内で直接答えてください。謝罪や前置き不要。"
    ),
}

# Few-shot examples: use generic content only — no brand names that could leak.
_FEWSHOT = {
    "zh": [
        {
            "role": "user",
            "content": "場景：\n偵測物件：person（near）、car（mid）\n畫面文字：（無文字）\n\n問題：前面有什麼？",
        },
        {"role": "assistant", "content": "前方有行人和車輛，行人距離很近，請注意。"},
        {
            "role": "user",
            "content": "場景：\n偵測物件：person（mid）\n畫面文字：「某商店」、「開放中」\n\n問題：前面那個招牌寫什麼？",
        },
        {"role": "assistant", "content": "前方招牌寫著「某商店」，目前開放中。"},
    ],
    "en": [
        {
            "role": "user",
            "content": "Scene:\nObjects: person (near), car (mid)\nText: (none)\n\nQuestion: What do I see in front of me?",
        },
        {"role": "assistant", "content": "There are pedestrians nearby and a car in the middle distance."},
    ],
    "ja": [
        {
            "role": "user",
            "content": "シーン：\n検出：person（near）、car（mid）\nテキスト：（なし）\n\n質問：前に何がありますか？",
        },
        {"role": "assistant", "content": "近くに歩行者がいて、中距離に車があります。"},
    ],
}

_NO_DETECT = {
    "zh": "（無偵測結果）",
    "en": "(no detections)",
    "ja": "（検出なし）",
}

_BAD_PATTERNS = {
    "zh": ["無法判斷", "無法回答", "無法確定", "沒有足夠", "不確定", "抱歉"],
    "en": ["cannot determine", "unable to", "not enough", "sorry", "i don't"],
    "ja": ["判断できません", "わかりません", "申し訳"],
}

# Sign / text-related question keywords — when these appear AND OCR is empty,
# skip Ollama entirely to avoid few-shot leakage and hallucinated sign content.
_SIGN_KEYWORDS = {
    "zh": ["招牌", "牌子", "寫什麼", "寫著", "字", "文字", "標誌", "標示"],
    "en": ["sign", "written", "text", "says", "say", "label"],
    "ja": ["看板", "書い", "文字", "標識"],
}

_NO_TEXT_REPLY = {
    "zh": "畫面中沒有可辨識的文字。",
    "en": "No readable text in the scene.",
    "ja": "画面に判別できる文字はありません。",
}


def _is_sign_question(question: str, lang: str) -> bool:
    lower = question.lower()
    return any(kw in lower for kw in _SIGN_KEYWORDS.get(lang, _SIGN_KEYWORDS["zh"]))


def _filter_ocr(ocr_results: list) -> list:
    """Remove timestamp watermarks and other noise from OCR results."""
    out = []
    for item in ocr_results:
        text = item[1] if isinstance(item, tuple) else item
        if _TIMESTAMP_RE.search(text):
            continue
        out.append(item)
    return out


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

    clean_ocr = _filter_ocr(ocr_results)
    if clean_ocr:
        texts = [r[1] for r in clean_ocr[:8] if r[1].strip()]
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


def _is_boilerplate(text: str, lang: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in _BAD_PATTERNS.get(lang, _BAD_PATTERNS["zh"]))


def _template_fallback(detections: list, lang: str) -> str:
    labels = list(dict.fromkeys(d[0] for d in detections[:3]))
    if not labels:
        return ""
    if lang == "zh":
        return "前方偵測到：" + "、".join(labels) + "。"
    if lang == "en":
        return "Detected in front: " + ", ".join(labels) + "."
    return "前方に検出：" + "、".join(labels) + "。"


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

    # No detections and no meaningful scene → skip Ollama, return empty.
    import omni_sense_ocr
    ocr_results = omni_sense_ocr.ocr_full_frame(frame)
    clean_ocr = _filter_ocr(ocr_results)

    if not detections and not clean_ocr:
        return {"zh": "前方目前無偵測到物件。", "en": "Nothing detected in front.", "ja": "前方に何も検出されていません。"}.get(lang, "")

    # Sign-question guard: if asking about a sign/text but OCR is empty, return fixed reply.
    if not clean_ocr and _is_sign_question(question, lang):
        return _NO_TEXT_REPLY.get(lang, _NO_TEXT_REPLY["zh"])

    context = _build_context(detections, clean_ocr, lang)
    system = _SYSTEM.get(lang, _SYSTEM["zh"])
    fewshot = _FEWSHOT.get(lang, _FEWSHOT["zh"])

    try:
        import ollama

        resp = ollama.chat(
            model=_OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system},
                *fewshot,
                {
                    "role": "user",
                    "content": f"場景：\n{context}\n\n問題：{question}",
                },
            ],
            options={"num_predict": 80, "temperature": 0.1},
            stream=False,
        )
        raw = resp["message"]["content"].strip()
        answer = _trim_to_sentence(raw)

        if _is_boilerplate(answer, lang) and detections:
            return _template_fallback(detections, lang)

        return answer
    except Exception:
        return ""
