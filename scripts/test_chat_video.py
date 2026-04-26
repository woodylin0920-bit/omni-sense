"""
Headless chat integration test on multiple video files.
No mic, no display window needed.

Usage:
  ~/venvs/omni-sense-venv/bin/python scripts/test_chat_video.py
"""
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

QUESTIONS = [
    ("zh", "前面有什麼？"),
    ("zh", "前面那個招牌寫什麼？"),
    ("zh", "現在安全嗎？"),
]

VIDEOS = [
    # Stable baseline: 5x 30s clips in samples/clips/ (Chinese signs / night / indoor / close-up).
    # Originals were archived to samples/archive/ (gitignored, ~100MB) — see docs/EVAL_REPORT.md.
    (str(_HERE / "samples" / "clips" / "taipei_walk_30s.mp4"),   [5, 15, 25]),
    (str(_HERE / "samples" / "clips" / "hk_night_30s.mp4"),      [5, 15, 25]),
    (str(_HERE / "samples" / "clips" / "subway_30s.mp4"),        [5, 15, 25]),
    (str(_HERE / "samples" / "clips" / "night_walk_30s.mp4"),    [5, 10, 18]),  # 22s only
    (str(_HERE / "samples" / "clips" / "store_indoor_30s.mp4"),  [2, 4, 6]),    # 7s only
]


def analyze_frame(model, frame_idx: int, frame, import_ocr, import_chat):
    import omni_sense_ocr
    import chat as chat_mod

    print(f"\n{'='*55}")
    print(f"  Frame #{frame_idx}  shape={frame.shape}")
    print(f"{'='*55}")

    # YOLO
    results = model(frame, verbose=False)
    r0 = results[0]
    detections = []
    for b in r0.boxes:
        label = r0.names[int(b.cls)]
        conf = float(b.conf)
        if conf >= 0.4:
            detections.append((label, "mid", conf, 0.5))
    labels = [d[0] for d in detections]
    from collections import Counter
    print(f"  YOLO: {dict(Counter(labels))}")

    # OCR
    t0 = time.perf_counter()
    ocr_out = omni_sense_ocr.ocr_full_frame(frame)
    ocr_ms = (time.perf_counter() - t0) * 1000
    texts = [r[1] for r in ocr_out]
    print(f"  OCR ({ocr_ms:.0f}ms): {texts[:6]}")

    # Chat Q&A
    for lang, question in QUESTIONS:
        t0 = time.perf_counter()
        answer = chat_mod.answer_query(question, frame, detections, lang=lang)
        ms = (time.perf_counter() - t0) * 1000
        print(f"  [{lang}] {question!r}")
        print(f"        → {answer!r}  ({ms:.0f}ms)")


def process_video(video_path: str, sample_secs: list, model, import_ocr, import_chat):
    import cv2
    name = Path(video_path).name
    print(f"\n{'#'*60}")
    print(f"# 影片：{name}")
    print(f"{'#'*60}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  ⚠️  無法開啟，跳過")
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"  {total} frames @ {fps:.0f}fps ({total/fps:.0f}s)")

    for sec in sample_secs:
        idx = min(int(sec * fps), total - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            print(f"  ⚠️ 無法讀第 {idx} 幀（{sec}s）")
            continue
        analyze_frame(model, idx, frame, import_ocr, import_chat)

    cap.release()


def main():
    from ultralytics import YOLO

    yolo_path = str(_HERE / "yolo26s.mlpackage")
    if not Path(yolo_path).exists():
        yolo_path = str(_HERE / "yolo26s.pt")
    print(f"Loading YOLO: {Path(yolo_path).name}")
    model = YOLO(yolo_path)

    import omni_sense_ocr
    import chat as chat_mod  # noqa: F401

    for video_path, sample_secs in VIDEOS:
        if not Path(video_path).exists():
            print(f"\n⚠️  跳過: {Path(video_path).name}（檔案不存在）")
            continue
        process_video(video_path, sample_secs, model, omni_sense_ocr, chat_mod)

    print(f"\n{'='*60}\n完成。")


if __name__ == "__main__":
    main()
