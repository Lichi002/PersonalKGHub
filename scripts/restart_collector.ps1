# 重启采集器（计划任务，提权）。非管理员会话运行会自动弹 UAC。
# 用途：改了 collector/ 代码后必须重启才生效；采集器疑似停摆时也用它。
$ErrorActionPreference = "Stop"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "restart_collector.log"
"[$(Get-Date -Format s)] restarting collector..." | Out-File $log -Append

schtasks /End   /TN PersonalKGHub-Collector 2>$null | Out-Null
Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue
Start-Sleep 2
schtasks /Run /TN PersonalKGHub-Collector | Out-Null
Start-Sleep 5
$ok = Get-Process pythonw -ErrorAction SilentlyContinue
"[$(Get-Date -Format s)] collector pythonw running: $([bool]$ok)" | Out-File $log -Append
