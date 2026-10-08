$ErrorActionPreference = 'Stop'
$player = 'C:\Program Files\BlueStacks_nxt\HD-Player.exe'
if (-not (Test-Path $player)) { throw 'BlueStacks player is not installed yet' }
$taskName = 'MHSY-Launch-Emulator'
# Use Task Scheduler COM: the ScheduledTasks CIM namespace is unavailable on this host.
$scheduler = New-Object -ComObject 'Schedule.Service'
$scheduler.Connect()
$folder = $scheduler.GetFolder('\')
$task = $scheduler.NewTask(0)
$task.RegistrationInfo.Description = 'Launch the MHSY Android emulator in the active desktop'
$task.Principal.UserId = 'user0-pc'
$task.Principal.LogonType = 3 # interactive token
$task.Principal.RunLevel = 1
$task.Settings.ExecutionTimeLimit = 'PT0S'
$task.Settings.DisallowStartIfOnBatteries = $false
$task.Settings.StopIfGoingOnBatteries = $false
$action = $task.Actions.Create(0)
$action.Path = $player
$action.Arguments = '--instance Rvc64 --cmd launchApp --package com.fl.mhsy.qihoo'
$registered = $folder.RegisterTaskDefinition($taskName, $task, 6, 'user0-pc', $null, 3)
$registered.Run($null) | Out-Null
Write-Output 'Launched BlueStacks Android 11 in the active desktop session'
