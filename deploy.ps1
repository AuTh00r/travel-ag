param(
    [switch]$SkipTests,
    [switch]$SkipPush,
    [string]$CommitMessage = ""
)

$ErrorActionPreference = "Stop"

# Remote shell is cmd.exe on Russian Windows — its default output codepage
# (OEM CP866) doesn't match what PowerShell expects from a child process,
# so raw ssh output renders as mojibake. Decoding as UTF-8 on our end only
# works once the remote side is also emitting UTF-8, hence "chcp 65001"
# prefixed on every remote command below.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$SSH_HOST = "sundita-office"
$REMOTE_DIR = "C:\travel-agent-bot"
$HEALTH_URL = "https://sundita.online/health"

function _ssh {
    param([string]$Cmd)
    ssh $SSH_HOST $Cmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed (exit: $LASTEXITCODE)" }
}

Write-Host "=== Travel Bot Deploy ===" -ForegroundColor Cyan
Write-Host ""

# 1. Commit & Push
if (-not $SkipPush) {
    Write-Host "[1/5] Commit & push..." -ForegroundColor Yellow

    $status = git status --porcelain
    if ($status) {
        if (-not $CommitMessage) {
            $CommitMessage = "deploy: $((Get-Date -Format 'yyyy-MM-dd HH:mm'))"
        }
        git add -A
        git commit -m $CommitMessage
    } else {
        Write-Host "      No changes to commit." -ForegroundColor Gray
    }

    git push origin master
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
    Write-Host "      Done" -ForegroundColor Green
} else {
    Write-Host "[1/5] Push skipped (--SkipPush)" - ForegroundColor Gray
}

# 2. Check SSH access
Write-Host "[2/5] Checking SSH access to server..." -ForegroundColor Yellow
_ssh "chcp 65001 >nul & echo SSH_OK"
Write-Host "      Done" -ForegroundColor Green

# 3. Pull + deps on server
Write-Host "[3/5] Updating code on server..." -ForegroundColor Yellow

# Никаких `if` внутри однострочных & -цепочек: проверено вживую (2026-07-09) —
# ssh на этом сервере обрывает выполнение всего, что идёт по цепочке & после
# любого if (exist/errorlevel, со скобками или без) — тихо, с кодом возврата 0,
# как будто всё прошло успешно. Вместо этого — отдельный _ssh-вызов на каждый
# шаг, код возврата берётся из exit code последней команды в цепочке (это
# работает надёжно, проверено), _ssh уже сам бросает исключение при ошибке.
_ssh "chcp 65001 >nul & cd /d $REMOTE_DIR & del /f .git\index.lock 2>nul & git pull origin master"
_ssh "chcp 65001 >nul & cd /d $REMOTE_DIR & .venv\Scripts\pip install -r requirements.txt -q"
Write-Host "      Done" -ForegroundColor Green

if (-not $SkipTests) {
    Write-Host "[4/5] Running tests on server..." -ForegroundColor Yellow
    _ssh "chcp 65001 >nul & cd /d $REMOTE_DIR & .venv\Scripts\python -m pytest tests -q 2>&1"
    Write-Host "      Tests passed" -ForegroundColor Green
} else {
    Write-Host "[4/5] Tests skipped (--SkipTests)" - ForegroundColor Gray
}

# 4. Restart bot
Write-Host "[5/5] Restarting bot..." -ForegroundColor Yellow
_ssh "chcp 65001 >nul & schtasks /run /tn RestartTravelBot"
Write-Host "      Done" -ForegroundColor Green

# 5. Health check
Write-Host ""
Write-Host "=== Health check ===" -ForegroundColor Cyan
$maxWaitSeconds = 30
$pollIntervalSeconds = 3
$elapsed = 0
$healthy = $false
while ($elapsed -lt $maxWaitSeconds) {
    Start-Sleep -Seconds $pollIntervalSeconds
    $elapsed += $pollIntervalSeconds
    try {
        $response = Invoke-WebRequest -Uri $HEALTH_URL -UseBasicParsing -TimeoutSec 5
        Write-Host $response.Content -ForegroundColor Green
        $healthy = $true
        break
    } catch {
        Write-Host "      Not ready yet (${elapsed}s)..." -ForegroundColor Gray
    }
}

if ($healthy) {
    Write-Host ""
    Write-Host "Deploy completed successfully!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "Health check failed after ${maxWaitSeconds}s." -ForegroundColor Red
    Write-Host "Check server manually via Chrome Remote Desktop." -ForegroundColor Yellow
    exit 1
}
