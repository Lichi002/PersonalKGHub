"""会话看门狗：监视页面心跳，界面关闭后自动停掉全部服务并自杀。

由 session_start.ps1 以 pythonw 分离拉起。判定依据 = /api/session 的
web_idle（前端每 10s 轮询 /api/stats 刷新；后端重启后返回 null，不误杀）。
睡眠唤醒误杀的规避：本次检查与上次检查的间隔本身超过阈值（说明看门狗
也睡过去了）→ 跳过判定。
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

PORT = 47600
LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "session_log.txt")
LOCK_PORT = 47699
CHECK_EVERY = 45      # 检查周期（秒）
FRESH_MAX = 150       # 页面心跳断超此值 = 界面已关闭
START_GRACE = 180     # 启动后这么久还没见过活跃页面 → 清理退出
NOWIN = 0x08000000    # CREATE_NO_WINDOW：pythonw 下 schtasks/netstat 不闪黑框


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


# 单实例锁：两个看门狗会双重停止
lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    lock.bind(("127.0.0.1", LOCK_PORT))
except OSError:
    log("another watchdog alive, exit")
    sys.exit(0)


def stop_all():
    log("stopping services")
    subprocess.run(["schtasks", "/End", "/TN", "PersonalKGHub-Collector"],
                   capture_output=True, creationflags=NOWIN)
    # 停完必须禁用：任务带 ONLOGON 触发器，不禁用的话下次登录会自启采集器
    subprocess.run(["schtasks", "/Change", "/TN", "PersonalKGHub-Collector",
                    "/DISABLE"], capture_output=True, creationflags=NOWIN)
    # 后端：按监听 47600 的 PID 杀整棵进程树（venv 启动器 + 解释器）
    out = subprocess.run(["netstat", "-ano"], capture_output=True,
                         text=True, creationflags=NOWIN).stdout
    for ln in out.splitlines():
        if f":{PORT} " in ln and "LISTENING" in ln:
            pid = ln.split()[-1]
            subprocess.run(["taskkill", "/F", "/T", "/PID", pid],
                           capture_output=True, creationflags=NOWIN)
            log(f"backend pid {pid} killed")
    log("all services stopped")


log("watchdog started")
ever_fresh = False
started = time.time()
last_check = time.time()

while True:
    time.sleep(CHECK_EVERY)
    now = time.time()
    if now - last_check > FRESH_MAX + CHECK_EVERY + 30:
        log("long gap between checks (system slept), skip")
        last_check = now
        continue
    last_check = now

    idle = None
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/api/session", timeout=5) as r:
            idle = json.loads(r.read().decode()).get("web_idle")
    except Exception:
        pass  # 后端不可达 → 视为 idle 无穷大

    if isinstance(idle, (int, float)) and idle < 60:
        ever_fresh = True

    if not ever_fresh:
        if now - started > START_GRACE:
            log("page never became active, cleanup")
            stop_all()
            break
        continue

    if idle is None:
        continue  # 后端刚重启还没收到页面心跳，暂不判定
    if idle > FRESH_MAX:
        log(f"web idle {idle:.0f}s > {FRESH_MAX}s, shutting down")
        stop_all()
        break
