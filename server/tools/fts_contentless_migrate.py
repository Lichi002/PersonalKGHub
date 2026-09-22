"""一次性迁移：FTS 改 contentless（去掉 1GB 冗余原文），索引从 contents 重建。

前置：先停掉 server 和 collector。运行后 fts_map 全部重指向新 rowid。
"""
import os
import sqlite3
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  file_pk UNINDEXED, path_name, content, tokenize='trigram',
  content='', contentless_delete=1
);
"""

from server.config import DB_PATH

db = sqlite3.connect(DB_PATH, timeout=60)
db.executescript("DROP TABLE IF EXISTS fts;")
db.executescript("DROP TABLE IF EXISTS fts_map;")
db.executescript(FTS_DDL)
db.executescript("""
CREATE TABLE IF NOT EXISTS fts_map(
  file_pk TEXT PRIMARY KEY,
  rid     INTEGER NOT NULL UNIQUE
) WITHOUT ROWID;
""")
db.commit()

rows = db.execute("""
  SELECT c.file_pk, f.path, c.text_zst
  FROM contents c JOIN files f ON f.volume || f.frn = c.file_pk
""").fetchall()
print("rebuilding fts from", len(rows), "docs", flush=True)

MAX_CHARS = 1_000_000
n = 0
for pk, path, text_zst in rows:
    text = zlib.decompress(text_zst).decode("utf-8")[:MAX_CHARS]
    cur = db.execute(
        "INSERT INTO fts(file_pk, path_name, content) VALUES(?,?,?)",
        (pk, path or "", text))
    db.execute("INSERT INTO fts_map(file_pk, rid) VALUES(?,?)",
               (pk, cur.lastrowid))
    n += 1
    if n % 1000 == 0:
        db.commit()
        print(" ", n, flush=True)
db.commit()
print("done:", n, flush=True)
