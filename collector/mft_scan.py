"""MFT 全量枚举：FSCTL_ENUM_USN_DATA（需管理员）。

产出与 dev_crawler 相同的记录 dict 流：
  {"v":"C:","t":"d","frn":...,"p":...,"n":...}
  {"v":"C:","t":"f","frn":...,"p":...,"n":"a.pdf","s":0,"m":epoch}
MFT 记录无文件大小，s=0（后续 os.stat 按需补）。
"""
import os
import struct

import pywintypes
import win32file
import winioctlcon

ERROR_HANDLE_EOF = 38  # 枚举结束的信号，非错误

import logging
_dbg = logging.getLogger("mft_scan")


def _query_next_usn(volume_handle) -> int:
    """FSCTL_QUERY_USN_JOURNAL，返回 NextUsn 作枚举上界。

    输出缓冲须 >= 4096（48 字节会报 1784）。
    """
    out = win32file.DeviceIoControl(
        volume_handle, winioctlcon.FSCTL_QUERY_USN_JOURNAL, None, 4096, None)
    return struct.unpack_from("<Q", out, 8)[0]  # NextUsn

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
FILE_SHARE_DELETE = 4
OPEN_EXISTING = 3

FILE_ATTRIBUTE_DIRECTORY = 0x10

RECORD_HEADER = struct.Struct("<IHHQQQqIIIIHH")  # USN_RECORD_V2 前 60 字节
HEADER_SIZE = RECORD_HEADER.size  # 60


def _open_volume(volume: str):
    handle = win32file.CreateFile(
        f"\\\\.\\{volume}", GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING, 0, None)
    return handle


def _filetime_to_epoch(ft: int) -> int:
    return int((ft - 116444736000000000) / 10_000_000)


def scan_volume(volume: str, ext_ok):
    """枚举整卷。ext_ok: 判断文件名是否入白名单的回调。

    yields 记录 dict；目录全 yield，文件按 ext_ok 过滤。
    """
    handle = _open_volume(volume)
    v = volume.rstrip(":").upper() + ":"
    try:
        # 根目录（记录 5）不在 ENUM 输出里，必须显式补一条，否则
        # 增量事件拼路径时会断在顶层目录（如 'Users' 的 parent 缺失）
        yield {"v": v, "t": "d", "frn": os.stat(volume + "\\").st_ino,
               "p": 0, "n": v + "\\", "s": 0, "m": 0}
        # MFT_ENUM_DATA_V0: StartFileReferenceNumber, LowUsn, HighUsn
        start_frn = 0
        call_n = 0
        # HighUsn 必须放开到 signed 最大值。曾用 QUERY 的 NextUsn——但
        # USN 日志被删除重建/截断后 NextUsn 回到低位，此前改动过的文件
        # 记录 USN 高于新 NextUsn，会被 ENUM 整体过滤掉（文件"隐身"，
        # 且被 scan_end 对账误判为已删除而清行）。全量扫描要的是"现存
        # 一切"，上界不设限；0/-1 才是特殊值（返回空集）。
        high_usn = (1 << 63) - 1
        _dbg.info("%s: HighUsn=%d", v, high_usn)
        while True:
            inbuf = struct.pack("<QQq", start_frn, 0, high_usn)
            try:
                outbuf = win32file.DeviceIoControl(
                    handle, winioctlcon.FSCTL_ENUM_USN_DATA, inbuf,
                    1 << 20, None)
            except pywintypes.error as e:
                if e.winerror == ERROR_HANDLE_EOF:
                    _dbg.info("%s: EOF after %d calls", v, call_n)
                    break
                raise
            call_n += 1
            if call_n <= 3:
                _dbg.info("%s call#%d: %d bytes, next_frn=%d, first16=%s",
                          v, call_n, len(outbuf),
                          struct.unpack_from("<Q", outbuf, 0)[0],
                          outbuf[:16].hex())
            start_frn = struct.unpack_from("<Q", outbuf, 0)[0]
            offset = 8
            while offset + HEADER_SIZE <= len(outbuf):
                (rec_len, major, minor, frn, pfrn, _usn, ft, _reason,
                 _src, _secid, attrs, name_len, name_off) = \
                    RECORD_HEADER.unpack_from(outbuf, offset)
                if rec_len == 0:
                    break
                name = outbuf[offset + name_off:offset + name_off + name_len]\
                    .decode("utf-16-le", errors="replace")
                is_dir = bool(attrs & FILE_ATTRIBUTE_DIRECTORY)
                if is_dir or ext_ok(name):
                    yield {
                        "v": v, "t": "d" if is_dir else "f",
                        "frn": frn, "p": pfrn, "n": name,
                        "s": 0, "m": _filetime_to_epoch(ft),
                    }
                offset += rec_len
            if start_frn == 0:
                break
    finally:
        win32file.CloseHandle(handle)
