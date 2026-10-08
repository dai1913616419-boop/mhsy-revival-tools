<#
Deploy launch-game-mode.ps1 and both APKs to C:\mhsy-local first, then run this
installer in Windows. It creates/updates only the two named desktop shortcuts.
It does not launch the emulator, install an APK, or touch any service/save/profile.
The existing MHSY Local Game shortcut retains its name and now routes to Demo;
MHSY Opening routes to the separate persistent USER opening profile.
#>
[CmdletBinding()]
param([string]$DesktopPath = 'C:\Users\user0-pc\Desktop')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$runtime = 'C:\mhsy-local'
$launcher = Join-Path $runtime 'launch-game-mode.ps1'
$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$player = 'C:\Program Files\BlueStacks_nxt\HD-Player.exe'
foreach ($required in @($launcher, $psExe, (Join-Path $runtime 'mhsy_local_latest.apk'), (Join-Path $runtime 'mhsy_opening.apk'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Deploy required file first: $required" }
}
if (-not (Test-Path -LiteralPath $DesktopPath -PathType Container)) { throw "Desktop directory does not exist: $DesktopPath" }
$desktop = [IO.Path]::GetFullPath($DesktopPath)
$shell = New-Object -ComObject 'WScript.Shell'
foreach ($spec in @(
    @{ Name = 'MHSY Local Game'; Mode = 'Demo'; Description = 'Existing local demo save; mode-safe APK selection' },
    @{ Name = 'MHSY Opening'; Mode = 'Opening'; Description = 'Opening tutorial; persistent separate USER profile' }
)) {
    $path = Join-Path $desktop ($spec.Name + '.lnk')
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $psExe
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Mode {1}' -f $launcher, $spec.Mode
    $shortcut.WorkingDirectory = $runtime
    $shortcut.Description = $spec.Description
    $shortcut.WindowStyle = 1
    if (Test-Path -LiteralPath $player -PathType Leaf) { $shortcut.IconLocation = $player + ',0' }
    $shortcut.Save()
    # Read back the route so COM failures cannot silently leave a wrong mode.
    $actual = $shell.CreateShortcut($path)
    if ($actual.TargetPath -ine $psExe -or $actual.Arguments -cne $shortcut.Arguments) {
        throw "Shortcut route verification failed: $path"
    }
    Write-Output "$path -> $($spec.Mode)"
}
Write-Output 'Shortcuts ready. No game or service was started. The launcher may request UAC when clicked.'
