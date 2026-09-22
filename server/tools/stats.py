"""M1 验证：输出各卷 files/dirs 计数与剪枝率。用法：
    python -m server.tools.stats
"""
import sys

from .. import config, tree
from ..schema import connect


def main():
    conn = connect()
    print(f"db: {config.DB_PATH}")
    for row in conn.execute(
            "SELECT volume, COUNT(*) FROM files GROUP BY volume"):
        print(f"  {row[0]} files: {row[1]}")
    for row in conn.execute(
            "SELECT volume, SUM(kept), COUNT(*) FROM dirs GROUP BY volume"):
        total = row[2]
        pct = row[1] / total * 100 if total else 0
        print(f"  {row[0]} dirs: {row[1]} kept / {total} ({pct:.1f}%)")
    # 抽查路径拼接
    sample = conn.execute(
        "SELECT path FROM files WHERE volume='D:' ORDER BY random() LIMIT 3"
    ).fetchall()
    for (p,) in sample:
        print(f"  sample: {p}")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
