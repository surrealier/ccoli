# Install a per-user logon task for the already provisioned local runtime.
# The task command contains only project paths; API credentials remain in server/.env.
$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $projectRoot 'output\nextgen-runtime'
$python = Join-Path $runtime 'Scripts\pythonw.exe'
$launcher = Join-Path $runtime 'run_server.py'
$taskName = 'ccoli Nextgen Agent'

if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
    -not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw 'Local nextgen runtime is missing. Provision output/nextgen-runtime before enabling autostart.'
}

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    $action = @($existing.Actions)[0]
    if ($existing.Actions.Count -ne 1 -or
        $action.Execute -ne $python -or
        $action.Arguments -ne ('"' + $launcher + '"') -or
        $action.WorkingDirectory -ne $projectRoot) {
        throw 'A scheduled task with this name already exists with different settings.'
    }
    Write-Output "Autostart already installed: $taskName"
    return
}

$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $launcher + '"') -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Start the local ccoli ESP32 agent when this user signs in.' | Out-Null
Write-Output "Autostart installed for user $user"
