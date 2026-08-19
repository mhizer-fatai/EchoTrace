$ErrorActionPreference = "Continue"

function Invoke-DockerCompose {
    param([string[]]$Arguments)
    docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

Invoke-DockerCompose @('down')

foreach ($path in @("hydradb-data\store", "hydradb-data\cache")) {
    if (Test-Path -LiteralPath $path) {
        Get-ChildItem -LiteralPath $path -Force | Remove-Item -Recurse -Force
    } else {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
    New-Item -ItemType File -Path "$path\.gitkeep" -Force | Out-Null
}

Invoke-DockerCompose @('up', '-d', '--build')
Write-Host "EchoTrace started with a fresh HydraDB store at http://localhost:8000"