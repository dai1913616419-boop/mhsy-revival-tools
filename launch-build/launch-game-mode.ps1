<#
Mode-safe launcher for the existing Windows runtime. Deploy, do not run from WSL.
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\mhsy-local\launch-game-mode.ps1 [-Mode Demo|Opening]
Demo is the default and uses the existing server\save.json unchanged by this script.
Opening always uses profiles\opening-user.json; never a QA or backup profile.
No uninstall, app-data clearing, profile import/reset, or save-file editing occurs.
Every launch installs the selected APK with -r and verifies its installed SHA256.
Services started here are ordinary hidden Python processes, not Windows services;
their PID and unique stdout/stderr paths are recorded under C:\mhsy-local\logs.
First desktop use can prompt for UAC. Existing unrelated listeners cause failure.
#>
[CmdletBinding()]
param([ValidateSet('Demo', 'Opening')][string]$Mode = 'Demo')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$runtime = 'C:\mhsy-local'
$server = Join-Path $runtime 'server'
$python = 'C:\Python312\python.exe'
$player = 'C:\Program Files\BlueStacks_nxt\HD-Player.exe'
$adb = 'C:\Program Files\BlueStacks_nxt\HD-Adb.exe'
$serial = 'emulator-5554'
$package = 'com.fl.mhsy.qihoo'
$interactiveUser = 'user0-pc'
$userProfile = Join-Path $server 'profiles\opening-user.json'
$apk = Join-Path $runtime $(if ($Mode -eq 'Opening') { 'mhsy_opening.apk' } else { 'mhsy_local_latest.apk' })
$logRoot = Join-Path $runtime 'logs'
$launcherLog = Join-Path $logRoot 'launch-game-mode.log'
$script:AppStopped = $false
$sessionTag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'

# The elevated child performs all work; no service/task action precedes elevation.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $child = Start-Process -FilePath $psExe -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath), '-Mode', $Mode)
    if ($null -eq $child.ExitCode) { throw 'Elevated launcher did not return an exit code' }
    exit $child.ExitCode
}

function Write-LaunchLog([string]$Message) {
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Mode, $Message
    Write-Host $line
    Add-Content -LiteralPath $launcherLog -Value $line -Encoding UTF8
}

# Tokenize Windows command lines, never evaluate them or infer ownership by substring.
if (-not ('MHSY.ModeArgv' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace MHSY {
  public static class ModeArgv {
    [DllImport("shell32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    static extern IntPtr CommandLineToArgvW(string commandLine, out int argc);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);
    public static string[] Parse(string commandLine) {
      int count; IntPtr p = CommandLineToArgvW(commandLine, out count);
      if (p == IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
      try {
        string[] result = new string[count];
        for (int i=0; i<count; ++i)
          result[i] = Marshal.PtrToStringUni(Marshal.ReadIntPtr(p, i * IntPtr.Size));
        return result;
      } finally { LocalFree(p); }
    }
  }
}
'@
}

function Same-Path([string]$A, [string]$B) {
    # IsPathRooted also accepts C:relative and \root-relative paths; their
    # meaning depends on the Python process cwd, which CIM does not provide.
    if ([string]::IsNullOrWhiteSpace($A) -or $A -notmatch '^[A-Za-z]:[\\/]') { return $false }
    if ([string]::IsNullOrWhiteSpace($B) -or $B -notmatch '^[A-Za-z]:[\\/]') { return $false }
    return [IO.Path]::GetFullPath($A).Equals([IO.Path]::GetFullPath($B), [StringComparison]::OrdinalIgnoreCase)
}

function Flag-Value([string[]]$Arguments, [string]$Flag, $Default) {
    $values = @()
    for ($i = 0; $i -lt $Arguments.Count; $i++) {
        if ($Arguments[$i] -eq $Flag) {
            if ($i + 1 -ge $Arguments.Count) { throw "Missing value for $Flag" }
            $values += $Arguments[++$i]
        } elseif ($Arguments[$i].StartsWith($Flag + '=', [StringComparison]::Ordinal)) {
            $values += $Arguments[$i].Substring($Flag.Length + 1)
        }
    }
    if ($values.Count -gt 1) { throw "Ambiguous duplicate option $Flag" }
    if ($values.Count -eq 1) { return $values[0] }
    return $Default
}

function Assert-OpeningArguments([string[]]$Arguments) {
    # argparse permits --prof/--por abbreviations and last-option-wins overrides.
    # Fail closed instead of claiming USER ownership from only one visible option.
    $seen = @{}
    for ($i = 0; $i -lt $Arguments.Count; $i++) {
        $token = $Arguments[$i]
        $equal = $token.IndexOf('=')
        if ($equal -ge 0) {
            $flag = $token.Substring(0, $equal)
            $value = $token.Substring($equal + 1)
        } else {
            $flag = $token
            if ($i + 1 -ge $Arguments.Count -or $Arguments[$i + 1].StartsWith('--', [StringComparison]::Ordinal)) { throw 'Missing opening CLI option value; refusing service changes' }
            $value = $Arguments[++$i]
        }
        if ($flag -cnotin @('--host', '--port', '--profile')) { throw 'Unknown or abbreviated opening CLI option; refusing service changes' }
        if ($seen.ContainsKey($flag)) { throw 'Duplicate opening CLI option; refusing service changes' }
        if ([string]::IsNullOrWhiteSpace($value)) { throw 'Empty opening CLI option value; refusing service changes' }
        $seen[$flag] = $true
    }
}

function Port-Owner([int]$Port) {
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -eq $Port })
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -eq 0) { return $null }
    if ($owners.Count -ne 1) { throw "Port $Port has multiple process owners; refusing changes" }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($owners[0])" -ErrorAction Stop
    if ($null -eq $owner) { throw "Port $Port owner disappeared; retry launch" }
    return $owner
}

function Owned-Identity($Owner, $Spec) {
    if ($null -eq $Owner -or -not (Same-Path $Owner.ExecutablePath $python) -or
        [string]::IsNullOrWhiteSpace($Owner.CommandLine)) { return $null }
    $arguments = [MHSY.ModeArgv]::Parse($Owner.CommandLine)
    $index = 1
    while ($index -lt $arguments.Count -and $arguments[$index] -in @('-u', '-B', '-E', '-s')) { $index++ }
    # Only the actual Python script position is accepted, not arbitrary later arguments.
    if ($index -ge $arguments.Count -or -not (Same-Path $arguments[$index] $Spec.Script)) { return $null }
    $options = @($arguments | Select-Object -Skip ($index + 1))
    if ($Spec.Name -eq 'opening') { Assert-OpeningArguments $options }
    if ((Flag-Value $options '--port' ([string]$Spec.Port)) -ne [string]$Spec.Port) { return $null }
    return [pscustomobject]@{ Process = $Owner; Arguments = $options }
}

function Invoke-Adb([string[]]$Arguments, [switch]$AllowFailure) {
    # PS5 native stderr must not bypass the explicit native exit-code check.
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $adb @Arguments 2>&1 | ForEach-Object { [string]$_ })
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    $text = ($output -join "`n").Trim()
    if ($code -ne 0 -and -not $AllowFailure) { throw "ADB exit $code ($($Arguments -join ' ')): $text" }
    return [pscustomobject]@{ ExitCode = $code; Text = $text }
}

function Run-InteractiveTask([string]$TaskName, [string]$Arguments) {
    # Same interactive-token COM pattern as launch-emulator.ps1; no CIM task API.
    $scheduler = New-Object -ComObject 'Schedule.Service'
    $scheduler.Connect()
    $folder = $scheduler.GetFolder('\')
    $task = $scheduler.NewTask(0)
    $task.RegistrationInfo.Description = 'MHSY mode launcher: interactive BlueStacks Rvc64'
    $task.Principal.UserId = $interactiveUser
    $task.Principal.LogonType = 3
    $task.Principal.RunLevel = 1
    $task.Settings.ExecutionTimeLimit = 'PT0S'
    # Boot can reuse a running player, but every game dispatch must run even
    # when a previous HD-Player action remains active. Global launcher mutex
    # serializes mode changes; BlueStacks controls its existing Rvc64 instance.
    $task.Settings.MultipleInstances = $(if ($TaskName -eq 'MHSY-Mode-GameLaunch') { 0 } else { 2 })
    $task.Settings.DisallowStartIfOnBatteries = $false
    $task.Settings.StopIfGoingOnBatteries = $false
    $action = $task.Actions.Create(0)
    $action.Path = $player
    $action.Arguments = $Arguments
    $registered = $folder.RegisterTaskDefinition($TaskName, $task, 6, $interactiveUser, $null, 3)
    $registered.Run($null) | Out-Null
}

function Stop-OwnedOpening($Identity, $Spec) {
    if ($Spec.Name -ne 'opening' -or $Spec.Port -ne 9003 -or -not (Same-Path $Spec.Script (Join-Path $server 'opening_server.py'))) { throw 'Only the canonical opening9003 listener may be switched' }
    if (-not $script:AppStopped) { throw 'Refusing profile service switch before confirmed app force-stop' }
    $original = $Identity.Process
    $process = Get-Process -Id $original.ProcessId -ErrorAction Stop
    $null = $process.Handle # Pin a process handle before checking against PID reuse.
    try {
        $again = Port-Owner $Spec.Port
        if ($null -eq $again -or $again.ProcessId -ne $original.ProcessId -or
            $again.CreationDate -ne $original.CreationDate -or
            $again.CommandLine -cne $original.CommandLine -or
            $null -eq (Owned-Identity $again $Spec)) { throw 'Opening service ownership changed; refusing termination' }
        Write-LaunchLog "Switching verified project opening listener PID $($original.ProcessId) to USER profile"
        $process.Kill()
        if (-not $process.WaitForExit(10000)) { throw 'Opening service did not exit within 10 seconds' }
    } finally { $process.Dispose() }
}

function Ensure-Service($Spec) {
    $owner = Port-Owner $Spec.Port
    if ($null -ne $owner) {
        $verified = Owned-Identity $owner $Spec
        if ($null -eq $verified) { throw "Port $($Spec.Port) is not owned by expected project script; no process was stopped" }
        if ($Spec.Name -eq 'opening') {
            $profile = Flag-Value $verified.Arguments '--profile' $null
            $hostValue = Flag-Value $verified.Arguments '--host' '0.0.0.0'
            if (-not (Same-Path $profile $userProfile) -or $hostValue -ne '0.0.0.0') {
                Stop-OwnedOpening $verified $Spec
                $owner = $null
            }
        }
        if ($null -ne $owner) {
            if ((Flag-Value $verified.Arguments '--host' '0.0.0.0') -ne '0.0.0.0') {
                throw "Existing $($Spec.Name) listener host is not 0.0.0.0; refusing to restart common/demo service"
            }
            Write-LaunchLog "Reusing $($Spec.Name) listener PID $($owner.ProcessId), port $($Spec.Port)"
            return
        }
    }
    if ($null -ne (Port-Owner $Spec.Port)) { throw "Port $($Spec.Port) changed ownership before service start" }
    $stdout = Join-Path $logRoot "$sessionTag-$($Spec.Name).stdout.log"
    $stderr = Join-Path $logRoot "$sessionTag-$($Spec.Name).stderr.log"
    $arguments = @('-u', ('"{0}"' -f $Spec.Script), '--host', '0.0.0.0', '--port', [string]$Spec.Port) + $Spec.Extra
    $previousEncoding = $env:PYTHONIOENCODING
    try {
        # Redirected Python logs otherwise use the Windows locale, breaking
        # Chinese startup messages on non-Chinese hosts. Inherit UTF-8 only here.
        $env:PYTHONIOENCODING = 'utf-8'
        $process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $server -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    } finally { $env:PYTHONIOENCODING = $previousEncoding }
    $process.Id | Set-Content -LiteralPath (Join-Path $logRoot "$sessionTag-$($Spec.Name).pid") -Encoding ASCII
    Write-LaunchLog "Started $($Spec.Name) PID $($process.Id); stdout=$stdout stderr=$stderr"
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        $process.Refresh()
        if ($process.HasExited) { throw "$($Spec.Name) exited $($process.ExitCode); see $stderr" }
        $listener = Port-Owner $Spec.Port
        if ($null -ne $listener) {
            $verified = Owned-Identity $listener $Spec
            if ($listener.ProcessId -ne $process.Id -or $null -eq $verified) { throw "Port $($Spec.Port) was claimed by a different process" }
            if ($Spec.Name -eq 'opening' -and -not (Same-Path (Flag-Value $verified.Arguments '--profile' $null) $userProfile)) { throw 'Started opening listener does not use USER profile' }
            Write-LaunchLog "$($Spec.Name) port $($Spec.Port) ready"
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "$($Spec.Name) listener timeout; see $stderr"
}

$mutex = [Threading.Mutex]::new($false, 'Global\MHSY-ModeLauncher')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Another mode launch is already in progress; wait and retry' }
    foreach ($file in @($python, $player, $adb, $apk, (Join-Path $server 'update_server.py'))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing required file: $file" }
    }
    $http = @{ Name = 'update'; Port = 80; Script = (Join-Path $server 'update_server.py'); Extra = @() }
    if ($Mode -eq 'Opening') {
        $game = @{ Name = 'opening'; Port = 9003; Script = (Join-Path $server 'opening_server.py'); Extra = @('--profile', ('"{0}"' -f $userProfile)) }
    } else {
        if (-not (Test-Path -LiteralPath (Join-Path $server 'save.json') -PathType Leaf)) { throw 'Demo save.json is missing; launcher will not bootstrap or overwrite it' }
        $game = @{ Name = 'game'; Port = 9001; Script = (Join-Path $server 'game_server.py'); Extra = @('--serial', '1', '--dyn-id', '1', '--born-pos', 'auto') }
    }
    if (-not (Test-Path -LiteralPath $game.Script -PathType Leaf)) { throw "Missing required file: $($game.Script)" }
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    Write-LaunchLog "Begin mode launch; APK=$apk"
    foreach ($spec in @($http, $game)) {
        $owner = Port-Owner $spec.Port
        if ($null -ne $owner -and $null -eq (Owned-Identity $owner $spec)) { throw "Unverified listener on port $($spec.Port); no process changes allowed" }
    }
    # Boot the emulator WITHOUT starting the package before the mode is verified.
    Run-InteractiveTask 'MHSY-Mode-EmulatorBoot' '--instance Rvc64'
    $deadline = (Get-Date).AddSeconds(120)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        $state = Invoke-Adb @('-s', $serial, 'get-state') -AllowFailure
        if ($state.ExitCode -eq 0 -and $state.Text -eq 'device') {
            $boot = Invoke-Adb @('-s', $serial, 'shell', 'getprop', 'sys.boot_completed') -AllowFailure
            if ($boot.ExitCode -eq 0 -and $boot.Text -eq '1') { $ready = $true; break }
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "ADB device $serial did not become ready within 120 seconds" }
    Invoke-Adb @('-s', $serial, 'shell', 'am', 'force-stop', $package) | Out-Null
    $running = Invoke-Adb @('-s', $serial, 'shell', 'pidof', $package) -AllowFailure
    if ($running.ExitCode -notin @(0, 1) -or $running.Text.Length -ne 0) { throw 'Could not confirm that the app was force-stopped' }
    $script:AppStopped = $true
    Write-LaunchLog 'App force-stopped before APK/profile switching'
    if ($Mode -eq 'Opening') { New-Item -ItemType Directory -Path (Split-Path $userProfile -Parent) -Force | Out-Null }
    Ensure-Service $http
    Ensure-Service $game
    $expectedHash = (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant()
    $install = Invoke-Adb @('-s', $serial, 'install', '-r', $apk)
    if ($install.Text -notmatch '(?m)^Success\s*$') { throw "APK install did not report Success: $($install.Text)" }
    $paths = Invoke-Adb @('-s', $serial, 'shell', 'pm', 'path', $package)
    $lines = @($paths.Text -split "`r?`n" | Where-Object { $_.Length -gt 0 })
    if ($lines.Count -ne 1 -or $lines[0] -notmatch '^package:(/data/app/[A-Za-z0-9_/=+~.\-]+/base\.apk)$') { throw "Unexpected installed APK path: $($paths.Text)" }
    $installedPath = $Matches[1]
    $fingerprint = Invoke-Adb @('-s', $serial, 'shell', 'sha256sum', ("'{0}'" -f $installedPath))
    if ($fingerprint.Text -notmatch '^([0-9A-Fa-f]{64})\s' -or $Matches[1].ToLowerInvariant() -ne $expectedHash) { throw 'Installed APK fingerprint differs from selected mode APK; refusing app launch' }
    Write-LaunchLog "Selected APK installed and fingerprint verified: $expectedHash"
    # Reverify listeners immediately before launching; never infer the opening profile from package presence.
    foreach ($spec in @($http, $game)) {
        $verified = Owned-Identity (Port-Owner $spec.Port) $spec
        if ($null -eq $verified) { throw "Listener identity changed on port $($spec.Port) before app launch" }
        if ($spec.Name -eq 'opening' -and -not (Same-Path (Flag-Value $verified.Arguments '--profile' $null) $userProfile)) { throw 'Opening profile changed before app launch' }
    }
    Run-InteractiveTask 'MHSY-Mode-GameLaunch' "--instance Rvc64 --cmd launchApp --package $package"
    $deadline = (Get-Date).AddSeconds(60)
    $started = $false
    while ((Get-Date) -lt $deadline) {
        $running = Invoke-Adb @('-s', $serial, 'shell', 'pidof', $package) -AllowFailure
        if ($running.ExitCode -eq 0 -and $running.Text -match '^\d+(?:\s+\d+)*$') { $started = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $started) { throw 'Interactive launch did not start the Android package within 60 seconds' }
    $script:AppStopped = $false
    Write-LaunchLog 'Android package started; close announcement and enter normally. Login/rendering still require UI verification; profiles remain server-owned.'
} catch {
    $message = $_.Exception.Message
    if (Test-Path -LiteralPath $logRoot -PathType Container) { Write-LaunchLog "FAILED: $message" } else { Write-Host "FAILED: $message" }
    Write-Error $message -ErrorAction Continue
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
