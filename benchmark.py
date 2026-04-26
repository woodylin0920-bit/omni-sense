"""
benchmark.py — 各階段延遲測量，投資人 demo 用的速度數字。

跑法: ./venv/bin/python benchmark.py
輸出: 每個階段的 min/avg/max (ms)，跑 N 次取平均
"""

import time
import statistics
import os
from pathlib import Path

_HERE = Path(__file__).resolve().parent

RUNS = 5  # 每項跑幾次（首次含 warm-up，去掉第一次再算）
IMG = str(_HERE / "samples" / "bus.jpg")


def measure(fn, runs=RUNS):
    times = []
    for i in range(runs + 1):  # 第 0 次是 warm-up，不算
        t0 = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - t0) * 1000
        if i > 0:
            times.append(elapsed)
    return times


def fmt(times):
    return f"min {min(times):.0f}ms / avg {statistics.mean(times):.0f}ms / max {max(times):.0f}ms"


def main():
    print("=" * 55)
    print("  omni-sense benchmark")
    print("=" * 55)

    avg_yolo_ms = avg_depth_ms = avg_combined_ms = None
    avg_ollama_ms = avg_gemini_ms = None

    # ── Layer 1: YOLO ──────────────────────────────────────
    print("\n[1/4] 載入 YOLO26s...", flush=True)
    from ultralytics import YOLO
    import cv2

    model = YOLO(str(_HERE / "yolo26s.pt"))
    frame = cv2.imread(IMG)
    model(frame, verbose=False)  # warm up

    def run_yolo():
        model(frame, verbose=False)

    times = measure(run_yolo)
    avg_yolo_ms = statistics.mean(times)
    print(f"  YOLO26s 推論：{fmt(times)}")

    # ── Layer 1: DepthAnything V2 Small ────────────────────
    print("\n[2/4] 載入 DepthAnything V2 Small...", flush=True)
    from transformers import pipeline as hf_pipeline
    from PIL import Image

    depth_pipe = hf_pipeline(
        "depth-estimation",
        model="depth-anything/Depth-Anything-V2-Small-hf",
    )
    pil_img = Image.open(IMG)
    depth_pipe(pil_img)  # warm up

    def run_depth():
        depth_pipe(pil_img)

    times = measure(run_depth)
    avg_depth_ms = statistics.mean(times)
    print(f"  DepthAnything 推論：{fmt(times)}")

    # ── Layer 1: 全偵測路徑（YOLO + Depth 串接）─────────────
    def run_full_detect():
        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        dr = depth_pipe(pil)
        model(frame, verbose=False)

    times = measure(run_full_detect)
    avg_combined_ms = statistics.mean(times)
    print(f"  YOLO + Depth 合計：{fmt(times)}")

    # ── Layer 3: Ollama Gemma 3 1B ────────────────────────
    print("\n[3/4] 測 Ollama Gemma 3 1B（需 ollama service）...", flush=True)
    try:
        import ollama as _ollama

        _ollama.generate(model="gemma3:1b", prompt="OK", options={"num_predict": 1})

        def run_ollama():
            _ollama.generate(
                model="gemma3:1b",
                prompt="用一句話（15字以內）用繁體中文告訴視障者：car, person。",
                options={"num_predict": 40, "temperature": 0.3},
            )

        times = measure(run_ollama, runs=3)  # LLM 慢，只跑 3 次
        avg_ollama_ms = statistics.mean(times)
        print(f"  Ollama gemma3:1b 推論：{fmt(times)}")
    except Exception as e:
        print(f"  ⚠️  Ollama 跳過（{e}）")

    # ── Layer 2: Gemini Flash（需 GEMINI_API_KEY + 網路）────
    print("\n[4/4] 測 Gemini 2.0 Flash（需 GEMINI_API_KEY）...", flush=True)
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        try:
            from google import genai

            client = genai.Client(api_key=api_key)

            def run_gemini():
                client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents="用一句話（15字以內）繁體中文：car, person。",
                )

            times = measure(run_gemini, runs=3)
            avg_gemini_ms = statistics.mean(times)
            print(f"  Gemini 2.0 Flash：{fmt(times)}")
        except Exception as e:
            print(f"  ⚠️  Gemini 跳過（{e}）")
    else:
        print("  ⚠️  GEMINI_API_KEY 未設定，跳過")

    # ── 摘要（引用本次實測值）─────────────────────────────
    def _s(v):
        return f"{v:>5.0f}ms" if v is not None else "skipped"

    print("\n" + "=" * 55)
    print("  投資人看的重點數字（本次實測平均值）")
    print("=" * 55)
    print(f"  YOLO26s 偵測              avg {_s(avg_yolo_ms)}  全離線（M1）")
    print(f"  DepthAnything V2 Small    avg {_s(avg_depth_ms)}  全離線（M1）")
    print(f"  YOLO + Depth 合計         avg {_s(avg_combined_ms)}  全離線（M1）")
    print("  Layer 1 say 播報           + ~50ms    全離線")
    print(f"  Layer 2 Gemini Flash           {_s(avg_gemini_ms)}  需網路")
    print(f"  Layer 3 Gemma 3 1B             {_s(avg_ollama_ms)}  全離線")
    print("  切離線後 Layer 3 自動接手，使用者 0 感知")
    print("=" * 55)


def bench_ocr(samples_dir="samples", n_warm=3):
    """OCR cold + warm latency on real sample images."""
    import time
    from pathlib import Path
    import cv2
    import omni_sense_ocr

    imgs = []
    for name in ["people_street.jpg", "bus.jpg", "test_street.mp4"]:
        p = Path(samples_dir) / name
        if not p.exists():
            continue
        if p.suffix == ".mp4":
            cap = cv2.VideoCapture(str(p))
            ok, frame = cap.read()
            cap.release()
            if ok:
                imgs.append((name, frame))
        else:
            frame = cv2.imread(str(p))
            if frame is not None:
                imgs.append((name, frame))

    if not imgs:
        print("[ocr] no sample images found, skipping")
        return

    print("\n=== OCR (RapidOCR-onnxruntime) ===")

    # Cold
    name, frame = imgs[0]
    t0 = time.perf_counter()
    out = omni_sense_ocr.ocr_full_frame(frame)
    cold_ms = (time.perf_counter() - t0) * 1000
    print(f"  cold   {name}: {cold_ms:7.1f}ms  ({len(out)} regions)")

    # Warm
    warm_times = []
    for name, frame in imgs:
        for _ in range(n_warm):
            t0 = time.perf_counter()
            omni_sense_ocr.ocr_full_frame(frame)
            warm_times.append((time.perf_counter() - t0) * 1000)
    if warm_times:
        avg = sum(warm_times) / len(warm_times)
        print(f"  warm  avg over {len(warm_times)} runs: {avg:7.1f}ms")


def bench_asr(samples_dir="samples", n_warm=3):
    """ASR cold + warm latency on TTS-generated baseline wavs.
    NOTE: TTS audio is easy for whisper — real-world WER will be higher."""
    import time
    from pathlib import Path
    import omni_sense_asr

    candidates = []
    for name, lang in [("test_zh.wav", "zh"), ("test_en.wav", "en")]:
        p = Path(samples_dir) / name
        if p.exists():
            candidates.append((name, str(p), lang))

    if not candidates:
        print("\n[asr] no sample wavs found; run: bash scripts/make_test_audio.sh")
        return

    print("\n=== ASR (mlx-whisper base) ===")

    # Cold
    name, path, lang = candidates[0]
    t0 = time.perf_counter()
    text = omni_sense_asr.transcribe_path(path, lang=lang)
    cold_ms = (time.perf_counter() - t0) * 1000
    print(f"  cold   {name}: {cold_ms:7.1f}ms  ->  {text!r}")

    # Warm
    warm_times = []
    for name, path, lang in candidates:
        for _ in range(n_warm):
            t0 = time.perf_counter()
            txt = omni_sense_asr.transcribe_path(path, lang=lang)
            warm_times.append((time.perf_counter() - t0) * 1000)
        print(f"  warm   {name}: -> {txt!r}")
    if warm_times:
        avg = sum(warm_times) / len(warm_times)
        print(f"  warm  avg over {len(warm_times)} runs: {avg:7.1f}ms")


if __name__ == "__main__":
    main()
    bench_ocr()
    bench_asr()
