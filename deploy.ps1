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
    Write-Host "[1/5] Push skipped (--SkipPush)" -ForegroundColor Gray
}

# 2. Check SSH access
Write-Host "[2/5] Checking SSH access to server..." -ForegroundColor Yellow

ssh -o ConnectTimeout=10 $SSH_HOST "chcp 65001 >nul & echo SSH_OK"
if ($LASTEXITCODE -ne 0) { throw "SSH unavailable. Check cloudflared and Cloudflare Access." }
Write-Host "      Done" -ForegroundColor Green

# 3. Pull + deps on server
Write-Host "[3/5] Updating code on server..." -ForegroundColor Yellow

$updateCmd = @"
chcp 65001 >nul
git config --global --add safe.directory $REMOTE_DIR 2>nul
cd $REMOTE_DIR
git pull origin master
.venv\Scripts\pip install -r requirements.txt -q
"@

ssh $SSH_HOST $updateCmd
if ($LASTEXITCODE -ne 0) { throw "Failed to update code on server" }
Write-Host "      Done" -ForegroundColor Green

if (-not $SkipTests) {
    Write-Host "[4/5] Running tests on server..." -ForegroundColor Yellow
    # Remote shell is cmd.exe (not PowerShell) — ";" is not a command separator there,
    # so this must be a newline-joined command, same pattern as $updateCmd above.
    $testCmd = @"
chcp 65001 >nul
cd $REMOTE_DIR
.venv\Scripts\python -m pytest tests -q 2>&1
"@
    ssh $SSH_HOST $testCmd
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Host "      Tests failed (exit code: $exitCode). Check manually via SSH." -ForegroundColor Red
        throw "Tests failed. Deploy aborted."
    }
    Write-Host "      Tests passed" -ForegroundColor Green
} else {
    Write-Host "[4/5] Tests skipped (--SkipTests)" -ForegroundColor Gray
}

# 4. Restart bot
Write-Host "[5/5] Restarting bot..." -ForegroundColor Yellow

ssh $SSH_HOST "chcp 65001 >nul & schtasks /run /tn RestartTravelBot"
if ($LASTEXITCODE -ne 0) { throw "Failed to restart bot" }
Start-Sleep -Seconds 3
Write-Host "      Done" -ForegroundColor Green

# 5. Health check
Write-Host ""
Write-Host "=== Health check ===" -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri $HEALTH_URL -UseBasicParsing -TimeoutSec 10
    Write-Host $response.Content -ForegroundColor Green
    Write-Host ""
    Write-Host "Deploy completed successfully!" -ForegroundColor Green
} catch {
    Write-Host "Health check failed: $_" -ForegroundColor Red
    Write-Host "Check server manually via Chrome Remote Desktop." -ForegroundColor Yellow
    exit 1
}

exit 0
