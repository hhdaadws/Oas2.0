Param(
  [string]$Port
)

# Move to repo root
$ScriptDir = Split-Path -Path $MyInvocation.MyCommand.Path -Parent
$RepoRoot = Split-Path -Path $ScriptDir -Parent
Set-Location $RepoRoot

# Ensure Python available
$HasPython = Get-Command python -ErrorAction SilentlyContinue
$HasPy = Get-Command py -ErrorAction SilentlyContinue
if (-not $HasPython -and -not $HasPy) {
  Write-Error "未检测到 Python。请安装 Python 3.10+。"
  exit 1
}

# Create venv if missing
if (-not (Test-Path ".venv")) {
  if ($HasPy) { & py -3 -m venv .venv } else { & python -m venv .venv }
}

# Use venv python directly (避免执行策略限制)
$VenvPy = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"

& $VenvPy -m pip install -U pip
& $VenvPy -m pip install -r requirements.txt

# Initialize .env if missing
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Copy-Item ".env.example" ".env"
}

# Determine port
if (-not $Port) { $Port = if ($env:API_PORT) { $env:API_PORT } else { "9001" } }

# Start backend
& $VenvPy -m uvicorn app.main:app --app-dir src --reload --host 0.0.0.0 --port $Port

