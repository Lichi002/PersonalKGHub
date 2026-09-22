"""会话启动（由 session_start.vbs 以管理员 pythonw 运行，全程无窗口零闪屏）。

流程：起后端 → 等端口 → 启用并运行采集器 → 起看门狗 → explorer 转交开浏览器。
所有控制台子进程带 CREATE_NO_WINDOW，避免 schtasks/netstat 闪黑框。
"""
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "session_log.txt")
NOWIN = 0x08000000  # CREATE_NO_WINDOW

sys.path.insert(0, ROOT)
from server import config  # noqa: E402

PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
PYW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def run(cmd):
    subprocess.run(cmd, capture_output=True, creationflags=NOWIN)


def listening(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        s.close()
        return True
    except OSError:
        return False


log("session start (vbs)")

# 1) 后端
if not listening(47600):
    log("starting backend")
    out = open(os.path.join(ROOT, "server_out.log"), "ab")
    err = open(os.path.join(ROOT, "server_err.log"), "ab")
    subprocess.Popen(
        [PY, "-m", "uvicorn", "server.main:app",
         "--host", "127.0.0.1", "--port", "47600"],
        cwd=ROOT, stdout=out, stderr=err, creationflags=NOWIN)
    for _ in range(20):
        time.sleep(1)
        if listening(47600):
            break
    log("backend listening" if listening(47600) else "backend FAILED to listen")
else:
    log("backend already running")

# 2) 采集器：任务平时 DISABLED，会话里启用+运行
run(["schtasks", "/Change", "/TN", "PersonalKGHub-Collector", "/ENABLE"])
run(["schtasks", "/Run", "/TN", "PersonalKGHub-Collector"])
log("collector enabled+run")

# 3) 看门狗：自带端口锁防重，盲起即可（已活着会自行退出）
subprocess.Popen([PYW, os.path.join(ROOT, "scripts", "session_watchdog.py")],
                 creationflags=NOWIN)
log("watchdog started")

# 4) 浏览器：经 explorer 转交回用户上下文（提权会话直接开 URL，页面 JS 不执行）
subprocess.Popen(["explorer.exe", "http://127.0.0.1:47600"], creationflags=NOWIN)
log("browser opened via explorer")
