"""
OCR 模組：在 YOLO bbox 內找文字。On-demand 使用（chat 觸發），
非 _detect 熱路徑，避免拖慢 Layer 1。
"""
from __future__ import annotations
import threading

_ocr_instance = None
_ocr_lock = threading.Lock()


def _get_ocr():
    """Lazy load。第一次呼叫 cold ~3-5s，之後快取在記憶體。"""
    global _ocr_instance
    if _ocr_instance is None:
        with _ocr_lock:
            if _ocr_instance is None:
                from rapidocr_onnxruntime import RapidOCR
                _ocr_instance = RapidOCR()
    return _ocr_instance


def ocr_text_in_box(frame, box_xyxy, min_conf: float = 0.5) -> list[str]:
    """
    在 frame 的 (x1,y1,x2,y2) 範圍內跑 OCR，回傳偵測到的文字 list。
    frame: numpy BGR (cv2 預設)
    box_xyxy: (x1, y1, x2, y2) tuple of int
    min_conf: 信心分數門檻
    """
    x1, y1, x2, y2 = [int(v) for v in box_xyxy]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return []
    crop = frame[y1:y2, x1:x2]
    ocr = _get_ocr()
    result, _ = ocr(crop)
    if not result:
        return []
    return [text for box, text, score in result if score >= min_conf]


def ocr_full_frame(frame, min_conf: float = 0.5) -> list[tuple[tuple[int, int, int, int], str, float]]:
    """整張 frame 跑 OCR，回 [(box_xyxy, text, score), ...]。
    chat 場景下若 YOLO 沒偵測到 sign 類別也能用。"""
    ocr = _get_ocr()
    result, _ = ocr(frame)
    if not result:
        return []
    out = []
    for box, text, score in result:
        if score < min_conf:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        xyxy = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
        out.append((xyxy, text, float(score)))
    return out
