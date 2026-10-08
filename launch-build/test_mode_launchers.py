"""Read-only launcher safety checks; never run either launcher/installer.

Requires the existing `ssh windows` connection. Windows PowerShell parses source
strings and executes ONLY the pure path/option helpers after an AST whitelist
check. No ADB, CIM process query, task registration, service, desktop, or file-write
action is invoked. All source transport is through stdin, without deployment.
Run: PYTHONDONTWRITEBYTECODE=1 python3 launch-build/test_mode_launchers.py
Actual Demo/Opening UI, UAC, installation and mode switches require parent QA.
"""
import base64
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
NAMES = ('launch-game-mode.ps1', 'install-mode-shortcuts.ps1')


def inspect_with_windows_parser(sources):
    entries = []
    for name, text in sources.items():
        encoded = base64.b64encode(text.encode('utf-8')).decode('ascii')
        entries.append({'Name': name, 'Encoded': encoded})
    # Do NOT dot-source whole files. Only parser/AST inspection runs here, plus
    # explicitly restricted helpers without external commands or side effects.
    script = "$inputs=ConvertFrom-Json ([Console]::In.ReadToEnd());\n" + r'''
$ErrorActionPreference='Stop'
$reports=@()
foreach($item in $inputs) {
  $source=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($item.Encoded))
  $tokens=$null; $errors=$null
  $ast=[System.Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
  if($errors.Count -ne 0) { throw (($errors | ForEach-Object { $_.Message }) -join '; ') }
  $commands=@($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]},$true) | ForEach-Object {
    $parent=$_.Parent
    while($null -ne $parent -and $parent -isnot [System.Management.Automation.Language.FunctionDefinitionAst]) {$parent=$parent.Parent}
    $function=if($null -eq $parent){''}else{$parent.Name}
    @{Name=$_.GetCommandName();Text=$_.Extent.Text;Function=$function}
  })
  $functions=@($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true))
  $report=@{Name=$item.Name;Commands=$commands;Functions=@($functions | ForEach-Object {@{Name=$_.Name;Text=$_.Extent.Text}})}
  if($item.Name -eq 'launch-game-mode.ps1') {
    foreach($fn in @($functions | Where-Object {$_.Name -in @('Same-Path','Flag-Value','Assert-OpeningArguments')})) {
      $external=@($fn.Body.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]},$true))
      if($external.Count -ne 0){throw 'Pure helper unexpectedly invokes external commands'}
      $calls=@($fn.Body.FindAll({param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst]},$true))
      foreach($call in $calls) {
        if($call.Member.Value -notin @('IsNullOrWhiteSpace','IsPathRooted','GetFullPath','Equals','StartsWith','Substring','IndexOf','ContainsKey')) {throw 'Helper method is outside read-only whitelist'}
      }
      . ([scriptblock]::Create($fn.Extent.Text))
    }
    $user='C:\mhsy-local\server\profiles\opening-user.json'
    if((Flag-Value @('--port','9003','--profile',$user) '--profile' $null) -cne $user){throw 'Profile argument parsing failed'}
    if((Flag-Value @('--profile='+$user) '--profile' $null) -cne $user){throw 'Equals-form profile parsing failed'}
    if((Flag-Value @('--host','0.0.0.0') '--port' '80') -ne '80'){throw 'Default option parsing failed'}
    if(-not (Same-Path 'c:\mhsy-local\server\profiles\opening-user.json' $user)){throw 'Case-insensitive absolute path comparison failed'}
    if(Same-Path 'profiles\opening-user.json' $user){throw 'Unverified relative profile was accepted'}
    if(Same-Path 'C:server\profiles\opening-user.json' $user){throw 'Drive-relative profile was accepted'}
    if(Same-Path '\mhsy-local\server\profiles\opening-user.json' $user){throw 'Root-relative profile was accepted'}
    if(Same-Path 'C:\mhsy-local\server\profiles\opening-qa.json' $user){throw 'Different profile was accepted'}
    Assert-OpeningArguments @('--host','0.0.0.0','--port=9003','--profile',$user)
    Assert-OpeningArguments @('--profile='+$user)
    foreach($bad in @(
      @('--profile',$user,'--prof','C:\qa.json'),
      @('--profile',$user,'--profile=C:\qa.json'),
      @('--port','9003','--por','9003'),
      @('--PROFILE',$user),
      @('--config','unused.json'),
      @('--profile'),
      @('--profile=')
    )) {
      $rejected=$false
      try { Assert-OpeningArguments $bad } catch {$rejected=$true}
      if(-not $rejected){throw 'Unsafe opening argv was accepted'}
    }
    $rejected=$false
    try { $null=Flag-Value @('--profile',$user,'--profile',$user) '--profile' $null } catch {$rejected=$true}
    if(-not $rejected){throw 'Duplicate profile option was accepted'}
    $rejected=$false
    try { $null=Flag-Value @('--profile') '--profile' $null } catch {$rejected=$true}
    if(-not $rejected){throw 'Missing profile value was accepted'}
    $report.Helpers='PASS'
  }
  $reports+=$report
}
ConvertTo-Json -InputObject $reports -Depth 7 -Compress
exit 0
'''
    # -Command - can discard unfinished multiline blocks at redirected EOF.
    # Execute the bounded inspection program with -EncodedCommand and transport
    # source files exclusively as inert JSON/base64 data on stdin instead.
    runner = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    result = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', 'windows', 'powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', runner],
        input=json.dumps(entries), text=True, capture_output=True, timeout=90,
    )
    if result.returncode != 0:
        raise AssertionError(f'Read-only Windows parser failed ({result.returncode}):\n{result.stdout}\n{result.stderr}')
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith('[{')]
    if len(lines) != 1:
        raise AssertionError(f'Expected one AST JSON report, got:\n{result.stdout}\n{result.stderr}')
    return {entry['Name']: entry for entry in json.loads(lines[0])}


class ModeLauncherSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: (ROOT / name).read_text(encoding='utf-8') for name in NAMES}
        cls.report = inspect_with_windows_parser(cls.sources)
        cls.launcher = cls.sources[NAMES[0]]
        cls.installer = cls.sources[NAMES[1]]
        cls.functions = {fn['Name']: fn['Text'] for fn in cls.report[NAMES[0]]['Functions']}

    def test_actual_windows_powershell_syntax_and_pure_helpers(self):
        self.assertEqual(set(self.report), set(NAMES))
        self.assertEqual(self.report[NAMES[0]]['Helpers'], 'PASS')

    def test_mode_apk_selection_and_default(self):
        self.assertIn("[ValidateSet('Demo', 'Opening')][string]$Mode = 'Demo'", self.launcher)
        self.assertIn("'mhsy_opening.apk'", self.launcher)
        self.assertIn("'mhsy_local_latest.apk'", self.launcher)
        self.assertIn("'install', '-r', $apk", self.launcher)
        self.assertIn('Installed APK fingerprint differs', self.launcher)
        self.assertLess(self.launcher.index("'install', '-r', $apk"), self.launcher.index("Run-InteractiveTask 'MHSY-Mode-GameLaunch'"))
        self.assertLess(self.launcher.index('fingerprint verified'), self.launcher.index("Run-InteractiveTask 'MHSY-Mode-GameLaunch'"))

    def test_no_destructive_profile_or_app_data_commands(self):
        forbidden = {'Remove-Item', 'Clear-Content', 'Copy-Item', 'Move-Item', 'Invoke-Expression', 'Start-Service', 'Stop-Service'}
        for report in self.report.values():
            commands = {cmd['Name'] for cmd in report['Commands']}
            self.assertFalse(commands & forbidden)
        self.assertNotIn("'uninstall'", self.launcher)
        self.assertNotIn("'clear'", self.launcher)
        self.assertNotIn("'rm'", self.launcher)
        self.assertIn("'profiles\\opening-user.json'", self.launcher)
        self.assertNotIn('opening-black.json', self.launcher)
        self.assertNotIn('opening-flash.json', self.launcher)

    def test_process_ownership_uses_executable_actual_script_and_port(self):
        owned = self.functions['Owned-Identity']
        self.assertIn('Same-Path $Owner.ExecutablePath $python', owned)
        self.assertIn('[MHSY.ModeArgv]::Parse($Owner.CommandLine)', owned)
        self.assertIn('Same-Path $arguments[$index] $Spec.Script', owned)
        self.assertIn("Flag-Value $options '--port'", owned)
        self.assertNotIn('-like', owned)
        self.assertIn('CommandLineToArgvW', self.launcher)

    def test_opening_argument_grammar_is_fail_closed_before_ownership(self):
        grammar = self.functions['Assert-OpeningArguments']
        self.assertIn("$flag -cnotin @('--host', '--port', '--profile')", grammar)
        self.assertIn('$seen.ContainsKey($flag)', grammar)
        self.assertIn('[string]::IsNullOrWhiteSpace($value)', grammar)
        owned = self.functions['Owned-Identity']
        self.assertLess(owned.index('Assert-OpeningArguments $options'), owned.index('Flag-Value $options'))

    def test_process_and_profile_paths_must_be_fully_qualified(self):
        same = self.functions['Same-Path']
        self.assertIn("'^[A-Za-z]:[\\\\/]'", same)
        self.assertIn('$A -notmatch', same)
        self.assertIn('$B -notmatch', same)
        self.assertNotIn('-not [IO.Path]::IsPathRooted', same)

    def test_utf8_child_environment_and_postdispatch_package_readiness(self):
        ensure = self.functions['Ensure-Service']
        self.assertIn("$env:PYTHONIOENCODING = 'utf-8'", ensure)
        self.assertIn('finally { $env:PYTHONIOENCODING = $previousEncoding }', ensure)
        task = self.functions['Run-InteractiveTask']
        self.assertIn("$TaskName -eq 'MHSY-Mode-GameLaunch'", task)
        self.assertIn('{ 0 } else { 2 }', task)
        dispatch = self.launcher.index("Run-InteractiveTask 'MHSY-Mode-GameLaunch'")
        self.assertIn("'pidof', $package", self.launcher[dispatch:])
        self.assertIn('if (-not $started)', self.launcher[dispatch:])
        self.assertLess(self.launcher.index('if (-not $started)', dispatch), self.launcher.index('$script:AppStopped = $false', dispatch))

    def test_only_opening_switch_can_terminate_a_verified_process(self):
        stop = self.functions['Stop-OwnedOpening']
        self.assertIn('if (-not $script:AppStopped)', stop)
        self.assertIn('$again.CreationDate -ne $original.CreationDate', stop)
        self.assertIn('$again.CommandLine -cne $original.CommandLine', stop)
        self.assertLess(stop.index('Owned-Identity $again $Spec'), stop.index('$process.Kill()'))
        self.assertEqual(self.launcher.count('$process.Kill()'), 1)
        ensure = self.functions['Ensure-Service']
        self.assertLess(ensure.index("$Spec.Name -eq 'opening'"), ensure.index('Stop-OwnedOpening'))
        self.assertLess(self.launcher.index("'am', 'force-stop'"), self.launcher.index('Ensure-Service $game'))
        self.assertIn('Global\\MHSY-ModeLauncher', self.launcher)

    def test_file_writes_are_only_launcher_logs_and_pid_records(self):
        writes = [cmd for cmd in self.report[NAMES[0]]['Commands'] if cmd['Name'] in ('Set-Content', 'Add-Content')]
        self.assertEqual(len(writes), 2)
        for cmd in writes:
            self.assertTrue('$launcherLog' in cmd['Text'] or '.pid' in cmd['Text'])
            self.assertNotIn('$userProfile', cmd['Text'])
            self.assertNotIn('save.json', cmd['Text'])
        self.assertIn('Demo save.json is missing; launcher will not bootstrap or overwrite it', self.launcher)

    def test_gui_launch_uses_interactive_com_tasks_not_cim_or_replacement_server(self):
        task = self.functions['Run-InteractiveTask']
        self.assertIn("New-Object -ComObject 'Schedule.Service'", task)
        self.assertIn('$task.Principal.LogonType = 3', task)
        self.assertIn('$task.Principal.UserId = $interactiveUser', task)
        self.assertIn('RegisterTaskDefinition', task)
        self.assertIn("Run-InteractiveTask 'MHSY-Mode-EmulatorBoot' '--instance Rvc64'", self.launcher)
        self.assertNotIn('Register-ScheduledTask', self.launcher)

    def test_native_exit_codes_and_hidden_service_logs_are_checked(self):
        native = self.functions['Invoke-Adb']
        self.assertIn('$code = $LASTEXITCODE', native)
        self.assertIn('$code -ne 0 -and -not $AllowFailure', native)
        self.assertIn('-Verb RunAs -Wait -PassThru', self.launcher)
        self.assertIn('exit $child.ExitCode', self.launcher)
        self.assertIn('-RedirectStandardOutput $stdout -RedirectStandardError $stderr', self.launcher)
        self.assertIn('$process.HasExited', self.launcher)

    def test_shortcut_installer_is_nonlaunching_and_keeps_demo_name(self):
        commands = {cmd['Name'] for cmd in self.report[NAMES[1]]['Commands']}
        self.assertNotIn('Start-Process', commands)
        self.assertNotIn('Invoke-Adb', commands)
        self.assertNotIn('Ensure-Service', commands)
        self.assertIn("Name = 'MHSY Local Game'; Mode = 'Demo'", self.installer)
        self.assertIn("Name = 'MHSY Opening'; Mode = 'Opening'", self.installer)
        self.assertIn('launch-game-mode.ps1', self.installer)
        self.assertIn('$actual.Arguments -cne $shortcut.Arguments', self.installer)


if __name__ == '__main__':
    unittest.main(verbosity=2)
