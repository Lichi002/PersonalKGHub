' KGHub 会话启动入口：ShellExecute "runas" 以管理员拉起 pythonw（无控制台，零闪屏）。
' 桌面快捷方式 → wscript.exe + 本脚本。路径全部从本脚本位置推导（仓库根 = scripts/..）。
On Error Resume Next

Dim fso, sh, root, logPath, lf, lf2
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
logPath = root & "\session_log.txt"

Set lf = fso.OpenTextFile(logPath, 8, True)
lf.WriteLine Now & " vbs fired"
lf.Close

Set sh = CreateObject("Shell.Application")
sh.ShellExecute root & "\.venv\Scripts\pythonw.exe", _
  """" & root & "\scripts\session_start.py""", _
  root, "runas", 0
If Err.Number <> 0 Then
  Set lf2 = fso.OpenTextFile(logPath, 8, True)
  lf2.WriteLine Now & " vbs ShellExecute error " & Err.Number & ": " & Err.Description
  lf2.Close
  Err.Clear
End If
