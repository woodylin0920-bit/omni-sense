"""
Omni-Sense Navigation Pipeline

架構：
  Layer 1: YOLO + 本地 TTS (macOS say)   <300ms 緊急播報
  Layer 2: Gemini Flash                  <500ms 自然語言（需網路）
  Layer 3: Ollama + Gemma 3 1B           <4s 離線 fallback（本地 LLM）

差異化：全離線 = 成本 + 延遲優勢
Demo 目標：可行性 + 速度
硬體：M1 Air 8GB（記憶體緊，用 1B Q4 模型）
"""

import time
import subprocess
import threading
import socket
from typing import Optional

from ultralytics import YOLO

# --- 設定 ---
YOLO_MODEL = "yolo26s.pt"
OLLAMA_MODEL = "gemma3:1b"
FRAME_STRIDE = 6  # 每 6 幀跑 1 次 pipeline（~5fps 分析 @ 30fps 輸入）

# 近/中/遠各自的 cooldown（秒）— 近距離車輛不能被抑制
COOLDOWN_BY_DIST = {"near": 0.5, "mid": 1.5, "far": 3.0, "unknown": 3.0}

# 危險類別：只有這些 label 會觸發播報（過濾桌椅等靜態物）
HIGH_PRIORITY_LABELS = {
    "person", "car", "bus", "truck", "motorcycle", "bicycle", "dog",
    "train", "horse", "cow", "sheep",
}

# --- 多語言模板（Layer 1 緊急播報）---
TEMPLATES = {
    "zh": {
        "person": "注意，前方有行人",
        "car": "注意，前方有車輛",
        "bus": "注意，前方有公車",
        "truck": "注意，前方有卡車",
        "bicycle": "注意，前方有腳踏車",
        "motorcycle": "注意，前方有機車",
        "dog": "注意，前方有狗",
        "default": "注意，前方有障礙物",
    },
    "en": {
        "person": "Warning, person ahead",
        "car": "Warning, car ahead",
        "bus": "Warning, bus ahead",
        "truck": "Warning, truck ahead",
        "bicycle": "Warning, bicycle ahead",
        "motorcycle": "Warning, motorcycle ahead",
        "dog": "Warning, dog ahead",
        "default": "Warning, obstacle ahead",
    },
    "ja": {
        "person": "注意、前方に人",
        "car": "注意、前方に車",
        "bus": "注意、前方にバス",
        "truck": "注意、前方にトラック",
        "bicycle": "注意、前方に自転車",
        "motorcycle": "注意、前方にバイク",
        "dog": "注意、前方に犬",
        "default": "注意、前方に障害物",
    },
}

# say 的語音代號
SAY_VOICE = {"zh": "Meijia", "en": "Samantha", "ja": "Kyoko"}

# Gemini API endpoint（用於 is_online 偵測真正要連的服務）
GEMINI_ENDPOINT_HOST = "generativelanguage.googleapis.com"
GEMINI_ENDPOINT_PORT = 443


# --- 網路偵測：測真正要連的 Gemini endpoint，不是 google.com ---
_network_ok = False
_last_check = 0.0


def check_network():
    """直接測 Gemini API endpoint 是否可達。2s timeout。"""
    global _network_ok, _last_check
    try:
        with socket.create_connection(
            (GEMINI_ENDPOINT_HOST, GEMINI_ENDPOINT_PORT), timeout=2
        ):
            _network_ok = True
    except (socket.timeout, OSError):
        _network_ok = False
    _last_check = time.time()


def is_online() -> bool:
    if time.time() - _last_check > 30:
        threading.Thread(target=check_network, daemon=True).start()
    return _network_ok


# --- TTS ---
def speak_local(text: str, lang: str = "zh"):
    """Layer 1 / Layer 3 本地 TTS（macOS say）。離線可用。"""
    voice = SAY_VOICE.get(lang, SAY_VOICE["zh"])
    subprocess.Popen(
        ["say", "-v", voice, "-r", "200", text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def speak_edge(text: str, lang: str = "zh"):
    """Layer 2 edge-tts，自然語音，但需要網路。"""
    import asyncio
    import edge_tts

    voice_map = {
        "zh": "zh-TW-HsiaoChenNeural",
        "en": "en-US-JennyNeural",
        "ja": "ja-JP-NanamiNeural",
    }
    voice = voice_map.get(lang, voice_map["zh"])

    async def _run():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save("/tmp/omni_tts.mp3")

    try:
        asyncio.run(_run())
        subprocess.Popen(
            ["afplay", "/tmp/omni_tts.mp3"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        # 失敗（離線、timeout）直接 fallback 到 say
        print(f"[TTS] edge-tts 失敗（{e}），改用本地 say")
        speak_local(text, lang)


# --- 距離估算 ---
def estimate_distance_depth(box, depth_map):
    """用 DepthAnything V2 深度圖估算距離。回 (label, depth_ratio)。"""
    import numpy as np

    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
    depth_arr = np.array(depth_map)
    region = depth_arr[y1:y2, x1:x2]
    if region.size == 0:
        return "unknown", None
    avg_depth = float(region.mean())
    max_d = float(depth_arr.max())
    ratio = avg_depth / max_d if max_d > 0 else 0.5
    if ratio < 0.35:
        return "near", round(ratio, 2)
    elif ratio < 0.65:
        return "mid", round(ratio, 2)
    return "far", round(ratio, 2)


# --- Layer 2: Gemini Flash ---
def gemini_describe(objects, lang: str = "zh") -> str:
    """雲端 LLM 場景描述。失敗回空字串。"""
    try:
        from google import genai
        import os

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return ""
        client = genai.Client(api_key=api_key)
        lang_name = {"zh": "繁體中文", "en": "English", "ja": "日本語"}.get(lang, "繁體中文")
        prompt = (
            f"視障導航助理。用一句話（15字以內）用{lang_name}告訴視障者：{', '.join(objects)}。"
        )
        resp = client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt
        )
        return resp.text.strip()
    except Exception as e:
        print(f"[Layer 2] Gemini 失敗：{e}")
        return ""


# --- Layer 3: 本地 Ollama + Gemma 3 1B ---
def ollama_describe(objects, lang: str = "zh") -> str:
    """離線 fallback：本地 LLM 生成場景描述。"""
    import ollama

    prompts = {
        "zh": f"視障導航助理。用一句話（15字以內）用繁體中文告訴視障者：{', '.join(objects)}。",
        "en": f"Visual navigation assistant. One sentence (<15 words) in English: {', '.join(objects)}.",
        "ja": f"視覚障害者のナビ。一言（15字以内）日本語で：{', '.join(objects)}。",
    }
    prompt = prompts.get(lang, prompts["zh"])
    try:
        resp = ollama.generate(
            model=OLLAMA_MODEL,
            prompt=prompt,
            options={"num_predict": 40, "temperature": 0.3, "keep_alive": "10m"},
        )
        return resp["response"].strip()
    except Exception as e:
        print(f"[Layer 3] Ollama 失敗：{e}")
        return ""


# --- 主 Pipeline ---
class OmniSensePipeline:
    def __init__(self, lang: str = "zh"):
        self.lang = lang
        self._last_alert: dict[tuple[str, str], float] = {}
        self._ollama_ready = False

        print("載入 YOLO26s...")
        self.model = YOLO(YOLO_MODEL)
        self.model("bus.jpg", verbose=False)  # warm up

        print("載入 DepthAnything V2...")
        from transformers import pipeline as hf_pipeline
        from PIL import Image

        self.depth_pipe = hf_pipeline(
            "depth-estimation",
            model="depth-anything/Depth-Anything-V2-Small-hf",
        )
        self.depth_pipe(Image.open("bus.jpg"))  # warm up

        print(f"Warm up Ollama {OLLAMA_MODEL}...")
        try:
            import ollama

            ollama.generate(
                model=OLLAMA_MODEL,
                prompt="OK",
                options={"num_predict": 1, "keep_alive": "10m"},
            )
            self._ollama_ready = True
        except Exception as e:
            print(f"  ⚠️  Ollama warm up 失敗（Layer 3 不可用）：{e}")

        print("Pipeline 就緒 (lang={})".format(lang))
        check_network()

    def set_language(self, lang: str):
        """Runtime 切換語言：zh / en / ja。"""
        if lang not in TEMPLATES:
            raise ValueError(f"不支援的語言: {lang}")
        self.lang = lang
        print(f"語言切換 → {lang}")

    def _cooldown(self, dist: str) -> float:
        return COOLDOWN_BY_DIST.get(dist, 3.0)

    def _should_alert(self, label: str, dist: str) -> bool:
        key = (label, dist)
        last = self._last_alert.get(key, 0)
        return time.time() - last > self._cooldown(dist)

    def _mark_alerted(self, label: str, dist: str):
        self._last_alert[(label, dist)] = time.time()

    def _templates(self):
        return TEMPLATES[self.lang]

    def _detect(self, frame):
        """YOLO + DepthAnything → 排序後的 detections list。
        Returns: list of (label, dist, conf, depth_val)
        """
        import cv2
        from PIL import Image

        # 縮到寬度 640px，保持比例 — 大幅降低 YOLO + Depth 延遲
        h0, w0 = frame.shape[:2]
        if w0 > 640:
            scale = 640 / w0
            frame = cv2.resize(frame, (640, int(h0 * scale)))

        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        t_depth = time.perf_counter()
        depth_result = self.depth_pipe(pil_img)
        depth_ms = (time.perf_counter() - t_depth) * 1000
        depth_map = depth_result["depth"]

        results = self.model(frame, verbose=False)

        # 整理所有偵測（含非 HIGH_PRIORITY，用於 summary 行）
        h, w = frame.shape[:2]
        r0 = results[0]
        spd = r0.speed  # preprocess / inference / postprocess (ms)

        detections = []
        all_obj_parts = []
        from collections import Counter
        all_labels = [r0.names[int(b.cls)] for b in r0.boxes if float(b.conf) >= 0.4]
        counts = Counter(all_labels)

        for r in results:
            for box in r.boxes:
                conf = float(box.conf)
                if conf < 0.4:
                    continue
                label = r.names[int(box.cls)]
                if label not in HIGH_PRIORITY_LABELS:
                    continue
                dist, depth_val = estimate_distance_depth(box, depth_map)
                detections.append((label, dist, conf, depth_val))

        # 組 summary 行：所有物件 + HIGH_PRIORITY 加距離標示
        dist_map = {(d[0], i): d[1] for i, d in enumerate(detections)}
        hp_dist: dict[str, list[str]] = {}
        for label, dist, _, _ in detections:
            hp_dist.setdefault(label, []).append(dist)

        obj_parts = []
        for label, cnt in counts.items():
            if label in hp_dist:
                dist_tags = "/".join(sorted(set(hp_dist[label])))
                obj_parts.append(f"{cnt} {label}{'s' if cnt > 1 else ''}({dist_tags})")
            else:
                obj_parts.append(f"{cnt} {label}{'s' if cnt > 1 else ''}")
        obj_str = ", ".join(obj_parts) if obj_parts else "no detections"

        print(f"0: {h}x{w} {obj_str}, {spd['inference']:.1f}ms")
        print(f"Speed: {spd['preprocess']:.1f}ms preprocess, {spd['inference']:.1f}ms inference, "
              f"{spd['postprocess']:.1f}ms postprocess, {depth_ms:.1f}ms depth "
              f"per image at shape (1, 3, {h}, {w})")

        # 畫框：YOLO 內建框 + 距離色彩疊加
        # 先排序，才知道誰是第一個（要播報的）
        dist_order = {"near": 0, "mid": 1, "far": 2, "unknown": 3}

        # 收集 HIGH_PRIORITY 偵測並記住 box 物件
        hp_boxes = []
        for r in results:
            for box in r.boxes:
                if float(box.conf) < 0.4:
                    continue
                label = r.names[int(box.cls)]
                if label not in HIGH_PRIORITY_LABELS:
                    continue
                dist, depth_val = estimate_distance_depth(box, depth_map)
                hp_boxes.append((label, dist, float(box.conf), depth_val, box))

        hp_boxes.sort(key=lambda x: (dist_order.get(x[1], 3), -x[2]))

        annotated = r0.plot()  # YOLO 標準藍框 + label + conf
        dist_color = {"near": (0, 0, 255), "mid": (0, 165, 255), "far": (0, 255, 0)}

        for i, (label, dist, conf, _, box) in enumerate(hp_boxes):
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            color = dist_color.get(dist, (255, 255, 255))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
            cv2.putText(annotated, dist, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            if i == 0:
                # 第一個（即將播報）：黃色粗框 + ★ 標記
                cv2.rectangle(annotated, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4),
                              (0, 255, 255), 5)
                cv2.putText(annotated, f"★ {label} ({dist})",
                            (x1, y2 + 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        self._last_annotated = annotated

        detections = [(l, d, c, dv) for l, d, c, dv, _ in hp_boxes]
        return detections

    def _annotate(self, frame):
        """只畫 YOLO 框（不跑 Depth），用於 stream 顯示。內部快取最新結果。"""
        import cv2
        results = self.model(frame, verbose=False)
        return results[0].plot()

    def process_frame(self, frame):
        """單幀處理：接 numpy BGR frame（cv2 預設格式）。"""
        detections = self._detect(frame)

        if not detections:
            return

        nearest_label, nearest_dist, nearest_conf, _ = detections[0]

        print("\n偵測：")
        for label, dist, conf, dval in detections:
            print(f"  {label:12s} | {dist:7s} | conf {conf:.2f} | depth {dval}")

        # Layer 1：本地 say 立即播報
        if self._should_alert(nearest_label, nearest_dist):
            templates = self._templates()
            text = templates.get(nearest_label, templates["default"])
            print(f"[Layer 1] {text}")
            speak_local(text, self.lang)
            self._mark_alerted(nearest_label, nearest_dist)

            # Layer 2/3 背景補充描述
            all_labels = [d[0] for d in detections[:3]]
            self._bg_thread = threading.Thread(
                target=self._background_describe,
                args=(all_labels,),
                daemon=True,
            )
            self._bg_thread.start()

    def _background_describe(self, labels):
        """Layer 2 線上優先 → 失敗 / 離線 fallback 到 Layer 3。"""
        desc = ""
        used_layer = 0
        print(f"[BG] online={is_online()} ollama_ready={self._ollama_ready}", flush=True)
        if is_online():
            t = time.perf_counter()
            desc = gemini_describe(labels, lang=self.lang)
            print(f"[Layer 2 耗時] {(time.perf_counter()-t)*1000:.0f}ms → {'有結果' if desc else '無結果'}", flush=True)
            if desc:
                used_layer = 2

        if not desc and self._ollama_ready:
            t = time.perf_counter()
            print("[Layer 3 開始]", flush=True)
            desc = ollama_describe(labels, lang=self.lang)
            print(f"[Layer 3 耗時] {(time.perf_counter()-t)*1000:.0f}ms", flush=True)
            if desc:
                used_layer = 3

        if desc:
            print(f"[Layer {used_layer}] {desc}")
            if used_layer == 2 and is_online():
                speak_edge(desc, lang=self.lang)
            else:
                # Layer 3 離線一定用 speak_local（edge-tts 需網路）
                speak_local(desc, lang=self.lang)

    def process_stream(self, source):
        """攝影機或影片檔連續流。source 接 int (camera index) 或 str (檔案路徑)。
        每 FRAME_STRIDE 幀抽 1 幀分析，避免撞 GPU。
        """
        import cv2

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise RuntimeError(f"無法開啟 video source: {source}")

        print(f"開始串流 (source={source}, 分析 stride={FRAME_STRIDE})")
        print("按 q 或 ESC 結束")

        frame_idx = 0
        annotated = None  # 最新一幀的 YOLO 畫框結果
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("串流結束")
                    break

                # 每 N 幀跑 1 次 pipeline，更新畫框
                if frame_idx % FRAME_STRIDE == 0:
                    try:
                        self.process_frame(frame)
                    except Exception as e:
                        print(f"[ERROR] process_frame: {e}")

                # Preview：有框用框，沒框用原始幀
                display = getattr(self, "_last_annotated", None)
                cv2.imshow("omni-sense", display if display is not None else frame)

                frame_idx += 1

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):  # q or ESC
                    break
                elif key == ord("1"):
                    self.set_language("zh")
                elif key == ord("2"):
                    self.set_language("en")
                elif key == ord("3"):
                    self.set_language("ja")
        finally:
            cap.release()
            cv2.destroyAllWindows()


# --- CLI ---
def main():
    import argparse
    import cv2

    ap = argparse.ArgumentParser(description="Omni-Sense 視障導航 pipeline")
    ap.add_argument("--source", default="0",
                    help="camera index (例 0) 或影片檔路徑（例 ./demo.mp4）或單張圖片")
    ap.add_argument("--lang", default="zh", choices=["zh", "en", "ja"],
                    help="初始語言，demo 時可用鍵盤 1/2/3 切換")
    args = ap.parse_args()

    pipe = OmniSensePipeline(lang=args.lang)

    # 嘗試把 source 轉成 int（camera index），失敗就當檔案路徑
    try:
        source = int(args.source)
    except ValueError:
        source = args.source

    # 單張圖片：用 process_frame
    if isinstance(source, str) and source.lower().endswith((".jpg", ".jpeg", ".png")):
        frame = cv2.imread(source)
        if frame is None:
            raise SystemExit(f"無法讀取圖片：{source}")
        pipe.process_frame(frame)
        # 顯示畫框結果視窗（按任意鍵關閉，但等 Layer 2/3 跑完）
        display = getattr(pipe, "_last_annotated", frame)
        cv2.imshow("omni-sense", display)
        bg = getattr(pipe, "_bg_thread", None)
        if bg and bg.is_alive():
            print("等待 Layer 2/3 回應中（最多 15 秒）...")
            bg.join(timeout=15)
        cv2.waitKey(1)
        cv2.destroyAllWindows()
        return

    # 攝影機或影片：用 process_stream
    pipe.process_stream(source)


if __name__ == "__main__":
    main()
