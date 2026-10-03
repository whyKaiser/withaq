$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python virtual environment' }
}
& .\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
& .\.venv\Scripts\python.exe -m pip install --no-deps -e .
if ($LASTEXITCODE -ne 0) { throw 'Project installation failed' }
npm.cmd --prefix apps/console ci --ignore-scripts
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
npm.cmd --prefix apps/console run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
& .\.venv\Scripts\python.exe -m pytest
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
Write-Output 'Ready: .\.venv\Scripts\python.exe scripts/lab.py (see README for PostgreSQL/packet mode)'
