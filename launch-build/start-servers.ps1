$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$runtime = 'C:\mhsy-local'
$server = Join-Path $runtime 'server'
$python = 'C:\Python312\python.exe'
# Only reuse or start this project's processes; never terminate other listeners.
$owned = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*C:\mhsy-local\server\*' -and $_.Name -eq 'python.exe' }
foreach ($spec in @(
    @{Name='update'; Script='update_server.py'; Args=@('--host','0.0.0.0','--port','80')},
    @{Name='game'; Script='game_server.py'; Args=@('--host','0.0.0.0','--port','9001','--serial','1','--dyn-id','1','--born-pos','auto')}
)) {
    if ($owned | Where-Object { $_.CommandLine -like "*$($spec.Script)*" }) {
        Write-Output "$($spec.Name) already running"
        continue
    }
    $p = Start-Process $python -ArgumentList (@('-u',(Join-Path $server $spec.Script)) + $spec.Args) -WorkingDirectory $server -RedirectStandardOutput (Join-Path $runtime "$($spec.Name).stdout.log") -RedirectStandardError (Join-Path $runtime "$($spec.Name).stderr.log") -WindowStyle Hidden -PassThru
    $p.Id | Set-Content (Join-Path $runtime "$($spec.Name).pid")
    Write-Output "$($spec.Name) PID $($p.Id)"
}
