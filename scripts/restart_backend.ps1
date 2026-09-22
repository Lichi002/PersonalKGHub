# 重启后端（uvicorn :47600）。非管理员会话运行会自动弹 UAC。
# 用途：改了 server/ 代码后必须重启才生效。路径从脚本位置推导。
$ErrorActionPreference = "Stop"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "restart_backend.log"
"[$(Get-Date -Format s)] restarting backend..." | Out-File $log -Append

$p = (Get-NetTCPConnection -LocalPort 47600 -State Listen -ErrorAction SilentlyContinue).OwningProcess
if ($p) { Stop-Process -Id $p -Force }
Start-Sleep 1
Start-Process -FilePath (Join-Path $root ".venv\Scripts\python.exe") `
    -ArgumentList "-m","uvicorn","server.main:app","--host","127.0.0.1","--port","47600" `
    -WorkingDirectory $root -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $root "server_out.log") `
    -RedirectStandardError (Join-Path $root "server_err.log")
Start-Sleep 5
$ok = Get-NetTCPConnection -LocalPort 47600 -State Listen -ErrorAction SilentlyContinue
"[$(Get-Date -Format s)] backend listening: $([bool]$ok)" | Out-File $log -Append
