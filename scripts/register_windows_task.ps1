# Registers a daily Windows Task Scheduler job to run refresh_data.py automatically.
param(
    [string]$TaskName = "IcelandMacroDashboardRefresh",
    [string]$RunAt = "09:00"
)

$RepoDir = Split-Path -Parent $PSScriptRoot
$PythonExe = "C:\Users\emorg\AppData\Local\Programs\Python\Python312\python.exe"
$ScriptPath = Join-Path $RepoDir "refresh_data.py"

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`" --trigger windows_task" -WorkingDirectory $RepoDir
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Daily primary data refresh for the Iceland Macroeconomic Monitor dashboard." -Force
Write-Host "Registered scheduled task '$TaskName' to run daily at $RunAt."
