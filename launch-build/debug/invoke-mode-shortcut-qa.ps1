# QA-only dispatch of an ACTUAL named desktop link in existing interactive session.
param([ValidateSet('Demo','Opening')][string]$Mode,
      [ValidateSet('D1','O1','D2','O2')][string]$Leg)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$child = 'C:\mhsy-local\run-mode-shortcut-child.ps1'
if (-not (Test-Path -LiteralPath $child -PathType Leaf)) { throw 'Missing QA child' }
$report = "C:\mhsy-local\logs\mode-qa-$Leg-launch.json"
if (Test-Path -LiteralPath $report) { throw 'Existing QA output; inspect rather than rerun completed leg' }
$scheduler = New-Object -ComObject 'Schedule.Service'
$scheduler.Connect()
$folder = $scheduler.GetFolder('\')
$name = "MHSY-QA-ModeShortcut-$Leg"
# Never overwrite a preexisting unrelated task; unique leg identifiers preserve QA.
try { $existing = $folder.GetTask($name) } catch { $existing = $null }
if ($null -ne $existing) { throw "Existing task $name; inspect before any reuse" }
$task = $scheduler.NewTask(0)
$task.RegistrationInfo.Description = "Temporary MHSY actual desktop shortcut QA $Leg"
$task.Principal.UserId = 'user0-pc'
$task.Principal.LogonType = 3
$task.Principal.RunLevel = 1
$task.Settings.ExecutionTimeLimit = 'PT10M'
$task.Settings.MultipleInstances = 2
$task.Settings.DisallowStartIfOnBatteries = $false
$task.Settings.StopIfGoingOnBatteries = $false
$action = $task.Actions.Create(0)
$action.Path = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$action.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $child + '" -Mode ' + $Mode + ' -Leg ' + $Leg
$action.WorkingDirectory = 'C:\mhsy-local'
$registered = $folder.RegisterTaskDefinition($name,$task,6,'user0-pc',$null,3)
$registered.Run($null) | Out-Null
Write-Output "Dispatched actual desktop-link QA $Leg/$Mode; inspect $report and native UI before next leg."
