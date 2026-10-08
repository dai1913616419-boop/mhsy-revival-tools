<# QA-only: launch the exact desktop shortcut inside user0-pc's interactive
session. The task uses that user's existing elevated token; this tests actual
shortcut routing/process/service survival, NOT the visible UAC prompt. #>
param([ValidateSet('Demo','Opening')][string]$Mode,
      [ValidateSet('D1','O1','D2','O2')][string]$Leg)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = 'C:\mhsy-local'
$report = Join-Path $root "logs\mode-qa-$Leg-launch.json"
if (Test-Path -LiteralPath $report) { throw "Preserve existing QA output: $report" }
$begin = (Get-Date).ToString('o')
try {
    $name = if ($Mode -eq 'Demo') {'MHSY Local Game'} else {'MHSY Opening'}
    $link = "C:\Users\user0-pc\Desktop\$name.lnk"
    $shell = New-Object -ComObject 'WScript.Shell'
    $actual = $shell.CreateShortcut($link)
    $expectedTarget = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $expectedArgs = '-NoProfile -ExecutionPolicy Bypass -File "C:\mhsy-local\launch-game-mode.ps1" -Mode ' + $Mode
    if ($actual.TargetPath -ine $expectedTarget -or $actual.Arguments -cne $expectedArgs) { throw 'Actual desktop shortcut route differs' }
    # Start-Process -Wait waits the descendant tree, including persistent ADB/services.
    # Windows completion seam: retain the direct process Handle, wait boundedly on
    # that process, then inspect ExitCode. Never wait for or stop its descendants.
    # Native UI and visible UAC verification remain separate from launcher completion.
    $process = Start-Process -FilePath $link -WorkingDirectory $root -PassThru
    $null = $process.Handle
    if (-not $process.WaitForExit(600000)) { throw 'Shortcut launcher did not exit within 600000 ms' }
    if ($null -eq $process.ExitCode) { throw 'Shortcut process exit code unavailable' }
    if ($process.ExitCode -ne 0) { throw "Shortcut launcher exited $($process.ExitCode)" }
    [ordered]@{leg=$Leg; mode=$Mode; begin=$begin; end=(Get-Date).ToString('o'); shortcut=$link; target=$actual.TargetPath; arguments=$actual.Arguments; process_id=$process.Id; exit_code=$process.ExitCode; session_id=[Diagnostics.Process]::GetCurrentProcess().SessionId; native_ui_verified=$false; uac_prompt_verified=$false} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
} catch {
    [ordered]@{leg=$Leg;mode=$Mode;begin=$begin;end=(Get-Date).ToString('o');error=$_.Exception.Message;native_ui_verified=$false;uac_prompt_verified=$false} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
    throw
}
