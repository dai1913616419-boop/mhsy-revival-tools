$ErrorActionPreference = 'Stop'
$installer = 'C:\Users\user0-pc\Downloads\BlueStacksFullInstaller_5.22.166.1003.exe'
$sig = Get-AuthenticodeSignature $installer
$sig | Format-List Status,StatusMessage,SignerCertificate
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Bluestack|now\.gg') {
    throw 'Installer publisher/signature validation failed'
}
$p = Start-Process -FilePath $installer -ArgumentList '-s','--defaultImageName','Rvc64','--imageToLaunch','Rvc64' -PassThru -Wait
Write-Output "Installer exit: $($p.ExitCode)"
exit $p.ExitCode
