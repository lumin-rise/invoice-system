import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # backend/
# 测试可通过环境变量把数据目录隔离开，避免污染真实会话数据
DATA_DIR = Path(os.environ.get("INVOICE_DATA_DIR") or BASE_DIR / "data")
UPLOAD_DIR = DATA_DIR / "uploads"
THUMB_DIR = DATA_DIR / "thumbs"
SESSION_FILE = DATA_DIR / "session.json"
TRACKER_FILE = DATA_DIR / "tracker.xlsx"            # 上传的基准 Tracker list
TRANSLATE_DIR = DATA_DIR / "translate"              # 翻译功能：原文 + 译文
TRANSLATE_DIR.mkdir(parents=True, exist_ok=True)

for p in (DATA_DIR, UPLOAD_DIR, THUMB_DIR):
    p.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_SIZE = 30 * 1024 * 1024          # 单文件上限 30MB
ALLOWED_EXT = {".pdf", ".ofd", ".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# 主题页标题（与现有 Tracker 保持一致）
REPORT_TITLE = "ZENDO - Travelling Expenses report"
