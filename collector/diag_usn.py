"""临时诊断：找出 FSCTL_QUERY_USN_JOURNAL / READ_USN_JOURNAL 的可行调用方式。"""
import ctypes
import ctypes.wintypes as wt
import logging
import struct

import pywintypes
import win32file
import winioctlcon

log = logging.getLogger("diag")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class USN_JOURNAL_DATA_V0(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in
                ("UsnJournalID", "NextUsn", "MinValidUsn", "MaxValidUsn",
                 "MaximumSize", "AllocationDelta")]


class READ_USN_JOURNAL_DATA_V1(ctypes.Structure):
    _fields_ = [("StartUsn", ctypes.c_ulonglong),
                ("ReasonMask", wt.DWORD), ("ReturnOnlyOnClose", wt.DWORD),
                ("Timeout", ctypes.c_ulonglong), ("BytesToWaitFor", ctypes.c_ulonglong),
                ("UsnJournalID", ctypes.c_ulonglong),
                ("MinMajorVersion", wt.DWORD), ("MaxMajorVersion", wt.DWORD)]


def run():
    volume = "C:"
    GENERIC_READ = 0x80000000
    SHARE = 1 | 2 | 4
    OPEN_EXISTING = 3

    for flags, tag in [(0, "flags=0"), (0x02000000, "backup_semantics")]:
        h = win32file.CreateFile(f"\\\\.\\{volume}", GENERIC_READ, SHARE,
                                 None, OPEN_EXISTING, flags, None)
        log.info("opened %s with %s -> handle ok", volume, tag)
        # 变体 A：pywin32 QUERY，不同输出大小
        for outsize in (48, 4096, 65536, 1 << 20):
            try:
                r = win32file.DeviceIoControl(
                    h, winioctlcon.FSCTL_QUERY_USN_JOURNAL, None,
                    outsize, None)
                log.info("pywin32 QUERY out=%d -> OK %d bytes", outsize, len(r))
                jd = struct.unpack("<QQQQQQ", r[:48])
                log.info("  journal_id=%d next_usn=%d", jd[0], jd[1])
                journal_id, next_usn = jd[0], jd[1]
            except pywintypes.error as e:
                log.info("pywin32 QUERY out=%d -> err %s", outsize, e)
                continue
            # QUERY 成功后立即试 READ（pywin32）
            for read_out in (65536, 1 << 20):
                inbuf = struct.pack("<qIIqqQ", next_usn, 0x80000203, 0, 0,
                                    1, journal_id)
                try:
                    r2 = win32file.DeviceIoControl(
                        h, winioctlcon.FSCTL_READ_USN_JOURNAL, inbuf,
                        read_out, None)
                    log.info("pywin32 READ out=%d -> OK %d bytes",
                             read_out, len(r2))
                except pywintypes.error as e:
                    log.info("pywin32 READ out=%d -> err %s", read_out, e)
            # ctypes READ V1
            try:
                rd = READ_USN_JOURNAL_DATA_V1(next_usn, 0x80000203, 0, 0, 1,
                                              journal_id, 0, 2)
                out = ctypes.create_string_buffer(0x10000)
                ret = wt.DWORD(0)
                ok = kernel32.DeviceIoControl(
                    ctypes.c_void_p(int(h)), 0x000900BB,
                    ctypes.byref(rd), ctypes.sizeof(rd),
                    out, 0x10000, ctypes.byref(ret), None)
                err = ctypes.get_last_error()
                log.info("ctypes READ -> ok=%s err=%d bytes=%d",
                         bool(ok), err, ret.value if ok else -1)
            except Exception as e:
                log.info("ctypes READ -> exc %s", e)
        win32file.CloseHandle(h)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from collector.collector import LOG_PATH  # noqa
    logging.basicConfig(filename=r"D:\PersonalKGHub\diag_log.txt",
                        level=logging.INFO,
                        format="%(asctime)s %(message)s")
    run()
