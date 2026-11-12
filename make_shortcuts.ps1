$wsh = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath('Desktop')
$projectDir = "d:\WorkPersonal\keyboard-mouse-switch"

$scController = $wsh.CreateShortcut("$desktop\Keyboard-Mouse Controller.lnk")
$scController.TargetPath = "$projectDir\start-controller.bat"
$scController.WorkingDirectory = $projectDir
$scController.Description = "Launch Keyboard and Mouse Controller"
$scController.Save()

$scReceiver = $wsh.CreateShortcut("$desktop\Keyboard-Mouse Receiver.lnk")
$scReceiver.TargetPath = "$projectDir\start-receiver.bat"
$scReceiver.WorkingDirectory = $projectDir
$scReceiver.Description = "Launch Keyboard and Mouse Receiver"
$scReceiver.Save()

Write-Output "Shortcuts created on Desktop."

