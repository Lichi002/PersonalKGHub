"""一次性回填：为已提取文档补标签（jieba TF-IDF，取前 50k 字符）。

后台运行即可，与 server 共存（busy_timeout 处理写锁）。
"""
import os
import sqlite3
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import tags as tagger  # noqa: E402

from server.config import DB_PATH

db = sqlite3.connect(DB_PATH, timeout=60)
db.execute("pragma busy_timeout=60000")

db.execute("DELETE FROM tags")  # 全量重算（旧标签是未调优版本）
db.commit()

rows = db.execute("""
  SELECT c.file_pk, c.text_zst FROM contents c
  JOIN files f ON f.volume || f.frn = c.file_pk
  WHERE f.status='extracted'
""").fetchall()
print("backfilling tags for", len(rows), "docs", flush=True)

t0 = time.time()
n = 0
for pk, text_zst in rows:
    try:
        text = zlib.decompress(text_zst).decode("utf-8")
    except Exception:
        continue
    words = tagger.extract_tags(text)
    if words:
        db.executemany("INSERT OR IGNORE INTO tags(file_pk, tag) VALUES(?,?)",
                       [(pk, t) for t in words])
    n += 1
    if n % 200 == 0:
        db.commit()
        print(" ", n, f"{time.time()-t0:.0f}s", flush=True)
db.commit()
print("done:", n, f"in {time.time()-t0:.0f}s", flush=True)
