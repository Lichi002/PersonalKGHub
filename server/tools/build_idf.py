"""一次性：从本机语料构建 IDF 文件（server/tags.py 使用）。

输出 D:\\PersonalKGHub\\data\\idf.txt，格式同 jieba 自带 idf.txt（word 值）。
值 = ln(N/df)：全语料常见词趋近 0（自然降权），领域专属词高。
"""
import math
import sqlite3
import sys
import zlib
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jieba  # noqa: E402

from server import config  # noqa: E402

from server.tags import is_noise, MAX_CHARS  # noqa: E402

db = sqlite3.connect(r"D:\PersonalKGHub\data\kghub.db", timeout=60)
db.execute("pragma busy_timeout=60000")

rows = db.execute("SELECT text_zst FROM contents").fetchall()
print("corpus docs:", len(rows), flush=True)

df = Counter()
for i, (text_zst,) in enumerate(rows, 1):
    try:
        text = zlib.decompress(text_zst).decode("utf-8")[:MAX_CHARS]
    except Exception:
        continue
    for tok in set(jieba.lcut(text)):
        if not is_noise(tok):
            df[tok] += 1
    if i % 500 == 0:
        print(" ", i, flush=True)

n = len(rows)
out = os.path.join(config.DATA_DIR, "idf.txt")
with open(out, "w", encoding="utf-8") as f:
    for word, freq in df.items():
        f.write(f"{word} {math.log(n / freq):.5f}\n")
print("idf terms:", len(df), "->", out, flush=True)
