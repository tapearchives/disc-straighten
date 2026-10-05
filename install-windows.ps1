# Create a shortcut to this extracted source kit; no administrator access required.
$kit = $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $desktop 'de-askew.lnk'))
$link.TargetPath = Join-Path $kit 'de-askew-gui.cmd'
$link.WorkingDirectory = $kit
$link.IconLocation = (Join-Path $kit 'assets/de-askew.ico') + ',0'
$link.Save()
Write-Output 'Created de-askew on your desktop. Keep the extracted source folder in place.'
