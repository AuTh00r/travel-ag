param(
    [switch]$SkipTests,
    [switch]$SkipPush,
    [string]$CommitMessage = ""
)

$ErrorActionPreference = "Stop"

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

ssh -o ConnectTimeout=10 $SSH_HOST "echo SSH_OK"
if ($LASTEXITCODE -ne 0) { throw "SSH unavailable. Check cloudflared and Cloudflare Access." }
Write-Host "      Done" -ForegroundColor Green

# 3. Pull + deps on server
Write-Host "[3/5] Updating code on server..." -ForegroundColor Yellow

$updateCmd = @"
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
    ssh $SSH_HOST "cd $REMOTE_DIR; .venv\Scripts\python -m pytest tests -q"
    if ($LASTEXITCODE -ne 0) { throw "Tests failed. Deploy aborted." }
    Write-Host "      Tests passed" -ForegroundColor Green
} else {
    Write-Host "[4/5] Tests skipped (--SkipTests)" -ForegroundColor Gray
}

# 4. Restart bot
Write-Host "[5/5] Restarting bot..." -ForegroundColor Yellow

ssh $SSH_HOST "schtasks /run /tn RestartTravelBot"
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
