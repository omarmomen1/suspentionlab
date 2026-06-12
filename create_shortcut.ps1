$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\SuspensionLab PRO.lnk")
$Shortcut.TargetPath = "C:\Users\omaar\Downloads\project\Start-SuspensionLab.bat"
$Shortcut.WorkingDirectory = "C:\Users\omaar\Downloads\project"
$Shortcut.IconLocation = "shell32.dll,25"
$Shortcut.Save()
