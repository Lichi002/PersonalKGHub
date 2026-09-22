# 会话停止：停采集器 + 后端 + 看门狗（看门狗也会自杀，重复调用无害）。
# 非管理员运行会自提权。路径从脚本位置推导（仓库根 = scripts/..）。
$ErrorActionPreference = "Continue"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "session_log.txt"
function L($m) { "[$(Get-Date -Format s)] $m" | Out-File $log -Append -Encoding utf8 }
L "session stop (manual)"

schtasks /End     /TN PersonalKGHub-Collector 2>$null | Out-Null
schtasks /Change  /TN PersonalKGHub-Collector /DISABLE | Out-Null

# pythonw 是本项目独占（采集器 + 看门狗），可全杀
Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue

# 后端：按命令行精确匹配 uvicorn（launcher + 解释器），不误伤其他 python
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'uvicorn' } |
    ForEach-Object { L "kill backend pid $($_.ProcessId)"
                     Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

L "session stopped"
