$ErrorActionPreference = "Stop"

docker compose down

foreach ($path in @("hydradb-data\store", "hydradb-data\cache")) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

docker compose up -d --build
Write-Host "EchoTrace started with a fresh HydraDB store at http://localhost:8000"
