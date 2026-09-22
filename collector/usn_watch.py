"""USN Journal 增量监听：FSCTL_READ_USN_JOURNAL（需管理员，pywin32 实现）。

实测要点：QUERY 的输出缓冲必须 >= 4096（本机返回 80 字节，48 字节会报
1784）；READ 输出缓冲 64KB 起步。

事件映射（on_record 回调）：
  op=upsert  文件创建/改名/内容变化（带 CLOSE），文件按 ext_ok 过滤
  op=delete  文件/目录删除
"""
import struct

import win32file
import winioctlcon

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
FILE_SHARE_DELETE = 4
OPEN_EXISTING = 3

FILE_ATTRIBUTE_DIRECTORY = 0x10

OUT_BUF_SIZE = 0x10000

REASON_FILE_CREATE = 0x00000100
REASON_FILE_DELETE = 0x00000200
REASON_DATA_EXTEND = 0x00000002
REASON_DATA_OVERWRITE = 0x00000001
REASON_RENAME_OLD = 0x00001000
REASON_RENAME_NEW = 0x00002000
REASON_CLOSE = 0x80000000

INTERESTING = (REASON_FILE_CREATE | REASON_FILE_DELETE | REASON_DATA_EXTEND |
               REASON_DATA_OVERWRITE | REASON_RENAME_OLD | REASON_RENAME_NEW)

RECORD_HEADER = struct.Struct("<IHHQQQqIIIIHH")  # USN_RECORD_V2 头 60 字节


def _open_volume(volume: str):
    return win32file.CreateFile(
        f"\\\\.\\{volume}", GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING, 0, None)


def query_journal(handle) -> tuple[int, int]:
    """返回 (journal_id, next_usn)。输出缓冲须 >= 4096。"""
    out = win32file.DeviceIoControl(
        handle, winioctlcon.FSCTL_QUERY_USN_JOURNAL, None, 4096, None)
    journal_id, next_usn = struct.unpack_from("<QQ", out, 0)
    return journal_id, next_usn


def watch_volume(volume: str, ext_ok, on_record):
    """阻塞式监听该卷的 USN 变更。volume 形如 'C:'。"""
    handle = _open_volume(volume)
    v = volume.rstrip(":").upper() + ":"
    try:
        journal_id, next_usn = query_journal(handle)
        # USN 是无符号 64 位（会超 2^63），全部用 Q
        # BytesToWaitFor=1：无新记录时阻塞，有任一字节即返回（实测 0xFFFF... 报 87）
        inbuf = struct.pack("<QIIQQQ", next_usn, INTERESTING, 0, 0,
                            1, journal_id)
        while True:
            raw = win32file.DeviceIoControl(
                handle, winioctlcon.FSCTL_READ_USN_JOURNAL, inbuf,
                OUT_BUF_SIZE, None)
            if len(raw) < 8:
                continue
            next_usn = struct.unpack_from("<Q", raw, 0)[0]
            inbuf = struct.pack("<QIIQQQ", next_usn, INTERESTING, 0, 0,
                                1, journal_id)
            offset = 8
            while offset + RECORD_HEADER.size <= len(raw):
                (rec_len, _mj, _mn, frn, pfrn, _usn, ft, reason, _src,
                 _secid, attrs, name_len, name_off) = \
                    RECORD_HEADER.unpack_from(raw, offset)
                if rec_len == 0:
                    break
                rec_start = offset
                offset += rec_len
                if not (reason & REASON_CLOSE):
                    continue
                name = raw[rec_start + name_off:
                           rec_start + name_off + name_len]\
                    .decode("utf-16-le", errors="replace")
                is_dir = bool(attrs & FILE_ATTRIBUTE_DIRECTORY)
                if reason & REASON_FILE_DELETE:
                    # 删除事件也按白名单过滤：系统里大量无关文件删除
                    # （ini/log/tmp…）不该逐条打到服务端
                    if is_dir or ext_ok(name):
                        on_record({"op": "delete", "v": v, "frn": frn,
                                   "t": "d" if is_dir else "f", "n": name})
                    continue
                if reason & (REASON_FILE_CREATE | REASON_RENAME_NEW |
                             REASON_DATA_EXTEND | REASON_DATA_OVERWRITE):
                    if is_dir or ext_ok(name):
                        on_record({
                            "op": "upsert", "v": v,
                            "t": "d" if is_dir else "f",
                            "frn": frn, "p": pfrn, "n": name,
                            "s": 0, "m": _filetime_to_epoch(ft),
                        })
    finally:
        win32file.CloseHandle(handle)


def _filetime_to_epoch(ft: int) -> int:
    return int((ft - 116444736000000000) / 10_000_000)
