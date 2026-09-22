"""一次性去重：同 (volume, path) 多行时，用 os.stat 的真实 st_ino 判定幸存者。

真实 FRN 匹配的行保留；都不匹配则保留 mtime 最新的一行；其余连同
contents/fts_map/fts 一并删除。
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server.config import DB_PATH  # noqa: E402

db = sqlite3.connect(DB_PATH, timeout=60)
db.execute("pragma busy_timeout=60000")

rows = db.execute(
    "SELECT volume, frn, name, path, mtime FROM files WHERE path != ''"
).fetchall()
groups = {}
for vol, frn, name, path, mtime in rows:
    groups.setdefault((vol, path), []).append((frn, mtime))

dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
print("dup groups:", len(dup_groups), flush=True)

killed = kept = 0
for (vol, path), members in dup_groups.items():
    try:
        live_ino = os.stat(path).st_ino
    except OSError:
        live_ino = None
    survivors = [f for f, _ in members if f == live_ino]
    if not survivors:  # 真身也不在册（路径也可能已失效）：保 mtime 最新
        survivors = [max(members, key=lambda m: m[1])[0]]
    for frn, _mt in members:
        if frn in survivors:
            kept += 1
            continue
        pk = vol + str(frn)
        r = db.execute("SELECT rid FROM fts_map WHERE file_pk=?",
                       (pk,)).fetchone()
        if r:
            db.execute("DELETE FROM fts WHERE rowid=?", (r[0],))
            db.execute("DELETE FROM fts_map WHERE file_pk=?", (pk,))
        db.execute("DELETE FROM contents WHERE file_pk=?", (pk,))
        db.execute("DELETE FROM files WHERE volume=? AND frn=?", (vol, frn))
        killed += 1
db.commit()
print("kept:", kept, "killed ghosts:", killed, flush=True)
