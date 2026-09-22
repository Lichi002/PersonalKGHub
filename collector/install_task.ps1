# 注册提权采集器计划任务（触发一次 UAC，需点"是"）
# 输出写入 D:\PersonalKGHub\install_log.txt 以便诊断
$log = "D:\PersonalKGHub\install_log.txt"
Start-Transcript -Path $log -Force

try {
  $projectRoot = Split-Path -Parent $PSScriptRoot
  $pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
  $collector = Join-Path $PSScriptRoot "collector.py"

  Write-Host "pythonw: $pythonw (exists: $(Test-Path $pythonw))"
  Write-Host "collector: $collector (exists: $(Test-Path $collector))"

  # 先彻底删除旧任务（清除调度器的僵尸实例记录），再全新创建
  schtasks /Delete /TN "PersonalKGHub-Collector" /F 2>$null
  Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue
  Start-Sleep 2

  schtasks /Create /F /TN "PersonalKGHub-Collector" `
    /TR "`"$pythonw`" `"$collector`"" `
    /SC ONLOGON /RL HIGHEST

  schtasks /Run /TN "PersonalKGHub-Collector"
  Write-Host "DONE"
} finally {
  Stop-Transcript
}
