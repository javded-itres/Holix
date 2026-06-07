# Install Helix CLI for the current user (Windows).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$py = $null
foreach ($name in @("py", "python3", "python")) {
    if (Get-Command $name -ErrorAction SilentlyContinue) {
        $py = $name
        break
    }
}
if (-not $py) {
    Write-Error "Python 3.14+ is required. Install from https://www.python.org/downloads/"
}

& $py "$Root\scripts\install.py" @args
exit $LASTEXITCODE