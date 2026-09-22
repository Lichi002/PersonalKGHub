Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|node|esbuild' } |
  ForEach-Object {
    $pp = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.ParentProcessId)" -ErrorAction SilentlyContinue).Name
    $cmd = $_.CommandLine
    if ($cmd) { $cmd = $cmd -replace '^(.{86}).*', '$1...' }
    '{0,-9} PID={1,-7} PPID={2,-9} {3}' -f $_.Name, $_.ProcessId, $pp, $cmd
  }
