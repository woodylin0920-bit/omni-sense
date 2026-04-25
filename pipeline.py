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
import tempfile
from pathlib import Path
from typing import Optional

# --- 設定 ---
_HERE = Path(__file__).resolve().parent
_WARMUP_IMG = _HERE / "bus.jpg"

YOLO_MODEL = str(_HERE / "yolo26s.pt")
OLLAMA_MODEL = "gemma3:1b"
FRAME_STRIDE = 6  # 每 6 幀跑 1 次 pipeline（~5fps 分析 @ 30fps 輸入）
MAX_DESC_AGE_SEC = {2: 1.2, 3: 20.0}  # Layer 2 (Gemini ~500ms) / Layer 3 (Gemma3 cold start 18s + buffer)

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

# 單一語音通道 + 優先級：Layer 1 (緊急警告) 絕不可被打斷
# priority 越小越優先。新播報若 priority > current，則跳過不搶。
PRIORITY_L1 = 1  # 緊急警告（macOS say）
PRIORITY_L2 = 2  # Gemini 描述（edge-tts）
PRIORITY_L3 = 3  # Ollama 描述（macOS say）

_audio_lock = threading.Lock()
_current_audio_proc = None
_current_audio_priority = 99  # 99 = 無音訊播放中
_current_audio_started = 0.0   # perf_counter 時戳，用於 TTL 判定
AUDIO_MAX_TTL_SEC = 15.0       # say/afplay 若卡住超過此時間視為僵屍，強制回收


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
def _stop_current_audio_unlocked():
    global _current_audio_proc, _current_audio_priority, _current_audio_started
    if _current_audio_proc is None:
        return
    if _current_audio_proc.poll() is None:
        try:
            _current_audio_proc.terminate()
            _current_audio_proc.wait(timeout=0.2)
        except Exception:
            try:
                _current_audio_proc.kill()
            except Exception:
                pass
    _current_audio_proc = None
    _current_audio_priority = 99
    _current_audio_started = 0.0


def _register_audio_proc_unlocked(proc, priority: int):
    global _current_audio_proc, _current_audio_priority, _current_audio_started
    _current_audio_proc = proc
    _current_audio_priority = priority
    _current_audio_started = time.perf_counter()


def _audio_alive_unlocked() -> bool:
    """當前音訊是否仍有效在播。若 proc 卡住超過 TTL，視為僵屍並強制回收。"""
    if _current_audio_proc is None:
        return False
    if _current_audio_proc.poll() is not None:
        return False
    if time.perf_counter() - _current_audio_started > AUDIO_MAX_TTL_SEC:
        print(f"[TTS] 音訊卡住 > {AUDIO_MAX_TTL_SEC}s，強制回收")
        _stop_current_audio_unlocked()
        return False
    return True


def speak_local(text: str, lang: str = "zh", priority: int = PRIORITY_L3):
    """Layer 1 / Layer 3 本地 TTS（macOS say）。離線可用。
    priority=PRIORITY_L1 為緊急警告（預設 L3 為描述）。
    若當前音訊 priority 更高，則跳過本次播報（不搶占）。
    """
    voice = SAY_VOICE.get(lang, SAY_VOICE["zh"])
    with _audio_lock:
        if _audio_alive_unlocked() and priority > _current_audio_priority:
            return  # 當前音訊優先級更高，不搶
        _stop_current_audio_unlocked()
        proc = subprocess.Popen(
            ["say", "-v", voice, "-r", "200", text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _register_audio_proc_unlocked(proc, priority)


def speak_edge(text: str, lang: str = "zh", priority: int = PRIORITY_L2) -> bool:
    """Layer 2 edge-tts，自然語音，但需要網路。每次產生唯一暫存檔避免並發覆蓋。
    回傳 True 表示已觸發播放；False 表示失敗或被更高優先級音訊擋下（呼叫端應 fallback）。
    """
    import asyncio
    import edge_tts

    voice_map = {
        "zh": "zh-TW-HsiaoChenNeural",
        "en": "en-US-JennyNeural",
        "ja": "ja-JP-NanamiNeural",
    }
    voice = voice_map.get(lang, voice_map["zh"])

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_path = tmp.name
    tmp.close()

    async def _run():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp_path)

    try:
        asyncio.run(_run())
        with _audio_lock:
            if _audio_alive_unlocked() and priority > _current_audio_priority:
                Path(tmp_path).unlink(missing_ok=True)
                return False  # 不搶占更高優先級
            _stop_current_audio_unlocked()
            proc = subprocess.Popen(
                ["afplay", tmp_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _register_audio_proc_unlocked(proc, priority)

        # 播放完後刪除暫存檔；若仍是目前音訊 proc 再清空指標
        def _cleanup(path: str, p):
            global _current_audio_proc, _current_audio_priority
            try:
                p.wait()
            finally:
                Path(path).unlink(missing_ok=True)
                with _audio_lock:
                    if _current_audio_proc is p:
                        _current_audio_proc = None
                        _current_audio_priority = 99
        threading.Thread(target=_cleanup, args=(tmp_path, proc), daemon=True).start()
        return True
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        print(f"[TTS] edge-tts 失敗（{e}），改用本地 say")
        speak_local(text, lang, priority=priority)
        return False


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


def estimate_distance_bbox(box, frame_h: int, frame_w: int) -> tuple[str, None]:
    """Coarse near/mid/far heuristic from bbox bottom position + area ratio.

    Used when depth map is unavailable (LLM inference in progress).
    Returns (dist_label, None) — second value matches estimate_distance_depth signature.
    """
    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
    bottom_y_ratio = y2 / frame_h
    bbox_area_ratio = (x2 - x1) * (y2 - y1) / (frame_h * frame_w)
    if bottom_y_ratio > 0.75 or bbox_area_ratio > 0.15:
        return "near", None
    elif bottom_y_ratio > 0.55 or bbox_area_ratio > 0.05:
        return "mid", None
    return "far", None


# --- Layer 2: Gemini Flash ---
def gemini_describe(objects, lang: str = "zh") -> str:
    """雲端 LLM 場景描述。失敗回空字串。"""
    import os
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""
    try:
        from google import genai
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
            options={"num_predict": 16, "temperature": 0.3, "keep_alive": "10m"},
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
        self._bg_thread: Optional[threading.Thread] = None
        self._bg_lock = threading.Lock()

        print("載入 YOLO26s...")
        from ultralytics import YOLO
        self.model = YOLO(YOLO_MODEL)
        self.model(str(_WARMUP_IMG), verbose=False)  # warm up

        print("載入 DepthAnything V2...")
        from transformers import pipeline as hf_pipeline
        from PIL import Image

        self.depth_pipe = hf_pipeline(
            "depth-estimation",
            model="depth-anything/Depth-Anything-V2-Small-hf",
            local_files_only=True,
        )
        self.depth_pipe(Image.open(_WARMUP_IMG))  # warm up

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
        """YOLO first → skip Depth if no HIGH_PRIORITY → faster Layer 1 + less CPU for Ollama.
        Returns: list of (label, dist, conf, depth_val)
        """
        import cv2
        from PIL import Image
        from collections import Counter

        # 縮到寬度 640px，保持比例
        h0, w0 = frame.shape[:2]
        if w0 > 640:
            scale = 640 / w0
            frame = cv2.resize(frame, (640, int(h0 * scale)))

        # ── Step 1: YOLO（快，~76-200ms warm）──────────────────
        results = self.model(frame, verbose=False)
        h, w = frame.shape[:2]
        r0 = results[0]
        spd = r0.speed

        all_labels = [r0.names[int(b.cls)] for b in r0.boxes if float(b.conf) >= 0.4]
        hp_raw = [lb for lb in all_labels if lb in HIGH_PRIORITY_LABELS]
        counts = Counter(all_labels)

        # ── Step 2: 沒有 HIGH_PRIORITY → 跳過 Depth，直接回傳 ──
        if not hp_raw:
            print(f"0: {h}x{w} no detections, {spd['inference']:.1f}ms")
            print(f"Speed: {spd['preprocess']:.1f}ms preprocess, {spd['inference']:.1f}ms inference, "
                  f"{spd['postprocess']:.1f}ms postprocess, 0ms depth (skipped)")
            self._last_annotated = r0.plot()
            return []

        # ── Step 3: 有 HIGH_PRIORITY → 才跑 Depth（Ollama 推理中則跳過）──
        bg_busy = self._bg_thread is not None and self._bg_thread.is_alive()

        if bg_busy:
            depth_map = None
            depth_ms = 0.0
        else:
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            t_depth = time.perf_counter()
            depth_result = self.depth_pipe(pil_img)
            depth_ms = (time.perf_counter() - t_depth) * 1000
            depth_map = depth_result["depth"]

        hp_boxes = []
        for r in results:
            for box in r.boxes:
                if float(box.conf) < 0.4:
                    continue
                label = r.names[int(box.cls)]
                if label not in HIGH_PRIORITY_LABELS:
                    continue
                if depth_map is not None:
                    dist, depth_val = estimate_distance_depth(box, depth_map)
                else:
                    dist, depth_val = estimate_distance_bbox(box, h, w)
                hp_boxes.append((label, dist, float(box.conf), depth_val, box))

        dist_order = {"near": 0, "mid": 1, "far": 2, "unknown": 3}
        hp_boxes.sort(key=lambda x: (dist_order.get(x[1], 3), -x[2]))

        # summary 行
        hp_dist: dict[str, list[str]] = {}
        for label, dist, _, _, _ in hp_boxes:
            hp_dist.setdefault(label, []).append(dist)
        obj_parts = []
        for label, cnt in counts.items():
            if label in hp_dist:
                dist_tags = "/".join(sorted(set(hp_dist[label])))
                obj_parts.append(f"{cnt} {label}{'s' if cnt > 1 else ''}({dist_tags})")
            else:
                obj_parts.append(f"{cnt} {label}{'s' if cnt > 1 else ''}")
        print(f"0: {h}x{w} {', '.join(obj_parts)}, {spd['inference']:.1f}ms")
        depth_note = "skipped (ollama_busy)" if bg_busy else f"per image at shape (1, 3, {h}, {w})"
        print(f"Speed: {spd['preprocess']:.1f}ms preprocess, {spd['inference']:.1f}ms inference, "
              f"{spd['postprocess']:.1f}ms postprocess, {depth_ms:.1f}ms depth {depth_note}")

        # 畫框
        annotated = r0.plot()
        dist_color = {"near": (0, 0, 255), "mid": (0, 165, 255), "far": (0, 255, 0)}
        for i, (label, dist, conf, _, box) in enumerate(hp_boxes):
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            color = dist_color.get(dist, (255, 255, 255))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
            cv2.putText(annotated, dist, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            if i == 0:
                cv2.rectangle(annotated, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4),
                              (0, 255, 255), 5)
                cv2.putText(annotated, f"★ {label} ({dist})",
                            (x1, y2 + 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        self._last_annotated = annotated
        return [(l, d, c, dv) for l, d, c, dv, _ in hp_boxes]

    def _annotate(self, frame):
        """只畫 YOLO 框（不跑 Depth），用於 stream 顯示。內部快取最新結果。"""
        import cv2
        results = self.model(frame, verbose=False)
        return results[0].plot()

    def process_frame(self, frame):
        """單幀處理：接 numpy BGR frame（cv2 預設格式）。"""
        t0 = time.perf_counter()
        detections = self._detect(frame)
        t_detect = (time.perf_counter() - t0) * 1000

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
            t_say = time.perf_counter()
            speak_local(text, self.lang, priority=PRIORITY_L1)
            t_say_ms = (time.perf_counter() - t_say) * 1000
            print(f"[Layer 1] {text}")
            print(f"  ⏱ 偵測→播報：{t_detect:.0f}ms｜say 觸發：{t_say_ms:.0f}ms（語音在背景播放）")
            self._mark_alerted(nearest_label, nearest_dist)

            # Layer 2/3 背景補充描述
            # 策略：忽略新請求（drop-if-busy）。同一時間只允許一個 worker，
            # 避免連續 alert 觸發多個 LLM 呼叫堆積。新請求來時若舊 worker 仍在跑則跳過。
            all_labels = [d[0] for d in detections[:3]]
            with self._bg_lock:
                if self._bg_thread is None or not self._bg_thread.is_alive():
                    self._bg_thread = threading.Thread(
                        target=self._background_describe,
                        args=(all_labels, t0, time.perf_counter()),
                        daemon=True,
                    )
                    self._bg_thread.start()

    def _background_describe(self, labels, t0=None, event_ts=None):
        """Layer 2 線上優先 → 失敗 / 離線 fallback 到 Layer 3。"""
        desc = ""
        used_layer = 0
        if is_online():
            t = time.perf_counter()
            desc = gemini_describe(labels, lang=self.lang)
            if desc:
                used_layer = 2
                elapsed = (time.perf_counter() - t) * 1000
                total = (time.perf_counter() - t0) * 1000 if t0 else 0
                print(f"  ⏱ Layer 2 Gemini：{elapsed:.0f}ms｜frame→播報總計：{total:.0f}ms")

        if not desc and self._ollama_ready:
            t = time.perf_counter()
            desc = ollama_describe(labels, lang=self.lang)
            if desc:
                used_layer = 3
                elapsed = (time.perf_counter() - t) * 1000
                total = (time.perf_counter() - t0) * 1000 if t0 else 0
                print(f"  ⏱ Layer 3 Ollama：{elapsed:.0f}ms｜frame→播報總計：{total:.0f}ms")

        if desc:
            # 描述回來太晚就丟棄，避免語音和目前畫面不同步
            # 用 perf_counter（monotonic）避免 NTP / 手動改時間造成誤判
            age_limit = MAX_DESC_AGE_SEC.get(used_layer, 1.2)
            if event_ts is not None:
                age = time.perf_counter() - event_ts
                if age > age_limit:
                    print(f"[Layer {used_layer}] 丟棄過期描述（{age:.1f}s > {age_limit}s）")
                    return
            print(f"[Layer {used_layer}] {desc}")
            t_tts = time.perf_counter()
            if used_layer == 2 and is_online():
                ok = speak_edge(desc, lang=self.lang, priority=PRIORITY_L2)
                if ok:
                    print(f"  ⏱ Layer 2 TTS (edge-tts)：{(time.perf_counter()-t_tts)*1000:.0f}ms 觸發")
                else:
                    # edge-tts 被 L1 擋下或失敗；fallback 到本地 say（但仍 L2 優先級，不搶 L1）
                    speak_local(desc, lang=self.lang, priority=PRIORITY_L2)
                    print(f"  ⏱ Layer 2 TTS fallback (say)：{(time.perf_counter()-t_tts)*1000:.0f}ms 觸發")
            else:
                speak_local(desc, lang=self.lang, priority=PRIORITY_L3)
                print(f"  ⏱ Layer 3 TTS (say)：{(time.perf_counter()-t_tts)*1000:.0f}ms 觸發")

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
