"""提权采集器入口：全量 MFT 枚举 → TCP 推送 → USN 增量监听。

需管理员运行（计划任务 /RL HIGHEST）。
协议（JSON lines 到 127.0.0.1:47610）：
  {"type":"scan","rec":{...}}         全量记录（分块）
  {"type":"scan_end"}                 全量结束，服务端触发剪枝
  {"type":"event","op":"upsert","rec":{...}} / {"op":"delete",...}
"""
import json
import logging
import os
import socket
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "collector_log.txt")
logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")


def _excepthook(tp, val, tb):
    log.critical("unhandled:\n%s", "".join(traceback.format_exception(tp, val, tb)))


sys.excepthook = _excepthook
threading.excepthook = lambda a: _excepthook(a.exc_type, a.exc_value, a.exc_traceback)

from server.config import DOC_EXTS, OFFICE_TEMP_PREFIX  # noqa: E402
from mft_scan import scan_volume  # noqa: E402
from usn_watch import watch_volume  # noqa: E402

HOST, PORT = "127.0.0.1", 47610
VOLUMES = ["C:", "D:"]

lock = threading.Lock()
sock = None


def ext_ok(name: str) -> bool:
    if name.startswith(OFFICE_TEMP_PREFIX):
        return False
    return os.path.splitext(name)[1].lower() in DOC_EXTS


def connect_server():
    global sock
    while True:
        try:
            s = socket.create_connection((HOST, PORT), timeout=10)
            s.settimeout(None)
            sock = s
            return s
        except OSError:
            log.warning("server %s:%s not up, retry in 5s", HOST, PORT)
            time.sleep(5)


def send_line(s, obj):
    s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))


def full_scan(s):
    t0 = time.time()
    n = 0
    for volume in VOLUMES:
        log.info("scanning %s via MFT...", volume)
        for rec in scan_volume(volume, ext_ok):
            with lock:  # 与 watch 线程共用 socket，防止 JSON 行交错
                send_line(s, {"type": "scan", "rec": rec})
            n += 1
    with lock:
        send_line(s, {"type": "scan_end"})
    log.info("scan done: %d records in %.1fs", n, time.time()-t0)


def drop_sock():
    """丢弃当前连接（置空 + 关闭），让下一轮心跳重连。"""
    global sock
    s, sock = sock, None
    if s is not None:
        try:
            s.close()
        except OSError:
            pass


def rescan_after_disconnect():
    """重连并重新全量。扫描中途再断线不致命——吞掉异常，交给下一轮心跳。

    异常绝不能冒出去：本函数由心跳线程调用，一旦抛出会直接结束采集器
    进程（服务端重启 → 采集器不告而别，实时增量静默停摆）。
    """
    try:
        full_scan(connect_server())
        log.info("rescan after reconnect done")
    except OSError as e:
        log.warning("rescan interrupted: %s, retry next heartbeat", e)
        drop_sock()


def ensure_connected():
    """主线程心跳：断线则重连并重新全量。"""
    while True:
        time.sleep(30)
        s = sock
        if s is None:
            rescan_after_disconnect()
            continue
        # 探活必须真写字节：sendall(b"") 是空操作，不碰 socket，探不出死连接。
        # 发一个空行即可——服务端对空行是 `if not line.strip(): continue`，安全。
        try:
            s.sendall(b"\n")
        except OSError:
            drop_sock()
            rescan_after_disconnect()


def on_record(rec):
    log.info("event: %s", json.dumps(rec, ensure_ascii=False))
    with lock:
        s = sock
        if s is None:
            return  # 已断线，等心跳线程重连全量
        try:
            send_line(s, {"type": "event", **rec})
        except OSError:
            # 断线：丢弃连接，等心跳线程重连全量（本事件丢失，靠重扫自愈）
            drop_sock()


def main():
    log.info("collector starting")
    if os.path.exists(r"D:\PersonalKGHub\run_diag.flag"):  # 临时诊断入口
        from diag_usn import run as _diag
        _diag()
        return
    connect_server()
    # 先启动监听再全量扫描：扫描期间的新增/删除事件不会丢
    # （upsert 幂等；扫描不会回插已删除文件的概率极低，下次扫描自愈）
    for volume in VOLUMES:
        threading.Thread(target=watch_volume_safe, args=(volume,),
                         daemon=True).start()
    while True:  # 全量扫描可能因服务端重启被打断，重试
        try:
            s = sock or connect_server()  # watcher 线程可能刚把 sock 置空
            full_scan(s)
            break
        except OSError as e:
            log.warning("full_scan interrupted: %s, retrying", e)
            drop_sock()
            time.sleep(5)
    ensure_connected()


def watch_volume_safe(volume):
    while True:
        try:
            watch_volume(volume, ext_ok, on_record)
        except Exception as e:
            log.error("watch %s error: %s, retry in 10s", volume, e)
            time.sleep(10)


if __name__ == "__main__":
    main()
