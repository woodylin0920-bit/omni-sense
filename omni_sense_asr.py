"""
ASR 模組：push-to-talk mic 錄音 → mlx-whisper 轉文字。
On-demand 使用（chat 觸發），非熱路徑，避免拖慢 Layer 1。

API:
- warmup_once(): 預先載 model（避免第一次 chat 卡 1-2s）
- record_fixed(duration_s): 錄固定秒數
- record_until(stop_event, max_s): 錄到 stop_event.set() 為止（push-to-talk 釋放）
- transcribe(audio_np, lang): 餵 numpy array 做轉錄
- transcribe_path(path, lang): 餵 wav/mp3 路徑（benchmark 用）
"""
from __future__ import annotations
import threading
import numpy as np

SAMPLE_RATE = 16000  # whisper 標準採樣率
MODEL_REPO = "mlx-community/whisper-base-mlx"

_model_warmed = False
_warmup_lock = threading.Lock()


def warmup_once():
    """第一次轉錄會載 model（cold ~1-2s）。pipeline 啟動時呼叫一次預熱。"""
    global _model_warmed
    if _model_warmed:
        return
    with _warmup_lock:
        if _model_warmed:
            return
        import mlx_whisper
        silent = np.zeros(SAMPLE_RATE, dtype=np.float32)  # 1s silence
        mlx_whisper.transcribe(
            silent,
            path_or_hf_repo=MODEL_REPO,
            language="en",
            verbose=False,
        )
        _model_warmed = True


def record_fixed(duration_s: float = 3.0) -> np.ndarray:
    """錄固定秒數音訊。回 mono float32 numpy array, 16kHz。"""
    import sounddevice as sd
    audio = sd.rec(
        int(duration_s * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    return audio.flatten()


def record_until(stop_event: threading.Event, max_s: float = 30.0) -> np.ndarray:
    """錄到 stop_event 被 set 為止（push-to-talk 釋放空白鍵），上限 max_s。
    回 mono float32 numpy array, 16kHz。"""
    import sounddevice as sd
    chunks = []
    chunk_s = 0.1
    chunk_n = int(chunk_s * SAMPLE_RATE)
    elapsed = 0.0
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
        while not stop_event.is_set() and elapsed < max_s:
            data, _overflow = stream.read(chunk_n)
            chunks.append(np.asarray(data).flatten())
            elapsed += chunk_s
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)


def transcribe(audio: np.ndarray, lang: str = "zh") -> str:
    """跑 mlx-whisper 轉錄。回去除前後空白的文字。空音訊回空字串。"""
    if audio.size == 0:
        return ""
    import mlx_whisper
    result = mlx_whisper.transcribe(
        audio.astype(np.float32),
        path_or_hf_repo=MODEL_REPO,
        language=lang,
        verbose=False,
    )
    return result.get("text", "").strip()


def transcribe_path(path: str, lang: str = "zh") -> str:
    """從 wav 檔轉錄（benchmark 用）。用 scipy 讀 wav → numpy，不需 ffmpeg。"""
    import scipy.io.wavfile as wav_io
    sr, data = wav_io.read(path)
    if data.dtype != np.float32:
        # int16 → float32 [-1, 1]
        data = data.astype(np.float32) / np.iinfo(data.dtype).max
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != SAMPLE_RATE:
        import scipy.signal
        samples = int(len(data) * SAMPLE_RATE / sr)
        data = scipy.signal.resample(data, samples).astype(np.float32)
    return transcribe(data, lang=lang)
