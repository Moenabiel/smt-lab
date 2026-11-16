# Windows setup. From this folder run:   powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment in .venv ..."
    $made = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("-3.12", "-3.13", "-3.11", "-3")) {
            py $v -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) { py $v -m venv .venv; $made = $true; break }
        }
    }
    if (-not $made) { python -m venv .venv }
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "`nRunning self-tests (look-ahead + fill-logic checks) ..."
& $py tests\test_lookahead.py
if ($LASTEXITCODE -ne 0) { throw "self-tests failed - do not trust any backtest until this passes" }

Write-Host "`nSetup OK. Smoke test next:"
Write-Host "  .\.venv\Scripts\python.exe make_synthetic.py"
Write-Host "  .\.venv\Scripts\python.exe run_backtest.py --a data\synth_NQ_1m.parquet --b data\synth_ES_1m.parquet"
