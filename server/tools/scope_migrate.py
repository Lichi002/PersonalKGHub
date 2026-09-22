"""一次性迁移：按路径圈定删除圈外文件行（含正文/FTS），重算剪枝。
运行：服务器重启后、collector 重启前执行一次。
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server.ingest import _rejected  # noqa: E402
from server.tree import rebuild      # noqa: E402

from server.config import DB_PATH

db = sqlite3.connect(DB_PATH, timeout=60)
db.execute("pragma busy_timeout=60000")

rows = db.execute("select volume, frn, name, path from files").fetchall()
victims = [(v, f) for v, f, n, p in rows if _rejected(p, n)]
print("files total:", len(rows), "out-of-scope:", len(victims), flush=True)

n_fts = 0
for v, f in victims:
    pk = v + str(f)
    r = db.execute("select rid from fts_map where file_pk=?", (pk,)).fetchone()
    if r:
        db.execute("delete from fts where rowid=?", (r[0],))
        db.execute("delete from fts_map where file_pk=?", (pk,))
        n_fts += 1
    db.execute("delete from contents where file_pk=?", (pk,))
    db.execute("delete from files where volume=? and frn=?", (v, f))
    if len(victims) >= 500 and (victims.index((v, f)) + 1) % 2000 == 0:
        db.commit()
        print("  deleted", victims.index((v, f)) + 1, flush=True)
db.commit()
print("fts rows removed:", n_fts, flush=True)

# 圈外目录已无文件，重算 kept 剪枝
print("rebuild:", rebuild(db), flush=True)
