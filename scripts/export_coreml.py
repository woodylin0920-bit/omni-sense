"""一次性 CoreML 匯出。產生 yolo26s.mlpackage（.gitignored，可重新產生）。

跑法: ./venv/bin/python scripts/export_coreml.py
預計耗時: 1-3 分鐘（M1 Air）
"""
from pathlib import Path

from ultralytics import YOLO

src = Path(__file__).resolve().parent.parent / "yolo26s.pt"
if not src.exists():
    raise SystemExit(f"找不到 {src}，請確認 yolo26s.pt 在 repo 根目錄。")

print(f"匯出 {src} → CoreML (nms=True)...")
model = YOLO(str(src))
model.export(format="coreml", nms=True)
out = src.with_suffix(".mlpackage")
print(f"匯出完成：{out}")
