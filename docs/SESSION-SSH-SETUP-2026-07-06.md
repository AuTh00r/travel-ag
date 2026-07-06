# SSH Setup Session — 2026-07-06

> **Status:** Incomplete — root cause of the blocker is now diagnosed, fix drafted but NOT YET APPLIED (needs admin session)  
> **Purpose:** Document every step taken so another AI can solve the remaining problem  
> **Remaining Blocker:** `deploy` user cannot `schtasks /run /tn RestartTravelBot` (access denied)
>
> **Update (2026-07-07, follow-up session):** Root cause found. See "Follow-up Diagnosis (2026-07-07)" section below. Issue 2 (pubkey auth) also confirmed RESOLVED — see that section.

---

## Project Context

- **Project:** Travel bot — Python/FastAPI chatbot for Instagram Direct
- **Repo:** `D:\projects\travel-agent-bot` (client) ↔ `C:\travel-agent-bot` (server)
- **Old VPS (dead):** `201.51.3.72` (Timeweb)
- **New server:** `93.125.10.160` (Timeweb)
- **Domain:** `sundita.online` (managed via Cloudflare)
- **Existing docs:**
  - `docs/DEPLOY-WINDOWS.md` — base server setup, tunnel, bot startup
  - `docs/SSH-REMOTE-ACCESS-SETUP.md` — SSH setup guide (needs update after this session)
  - `deploy.ps1` — deploy script (uses `schtasks /run` to restart bot — line 71)

---

## Server Info

| Property | Value |
|----------|-------|
| OS | Windows (Russian language) |
| Computer name | `SST` |
| Main user | `Бухгалтер 3` (non-admin, auto-login, runs the bot) |
| Built-in admin | `Администратор` (Russian) |
| Bot path | `C:\travel-agent-bot` |
| Bot start | `C:\travel-agent-bot\start-bot.vbs` (VBS script → uvicorn) |
| Python venv | `C:\travel-agent-bot\.venv` |
| `.env` | Present with all secrets |
| Git | Installed at `C:\Program Files\Git` |
| cloudflared | Running — `sundita.online` works |
| Cloudflare Access App for SSH | **NOT configured** (bare tunnel route exists but no Access policy yet) |

---

## Client (Office PC) Info

| Property | Value |
|----------|-------|
| OS | Windows |
| Username | `AUTHOR` |
| Shell | PowerShell |
| OpenSSH | `OpenSSH_9.5p1` (bundled with Windows) |
| Git | 2.54 |
| Repo | `D:\projects\travel-agent-bot` |
| cloudflared | Installed via `winget install --id Cloudflare.cloudflared` |
| SSH key | `~\.ssh\id_ed25519_travelbot` (ed25519, public at `.pub`) |
| Key comment | `author@DESKTOP-GMF1SLG` |

---

## Step-by-Step Setup

### Step 1: Cloudflare Tunnel Route for SSH

Connected to server via Chrome Remote Desktop under `Бухгалтер 3`.

**Enable OpenSSH Server** (PowerShell as admin):

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
```

**Start service, set to Automatic:**

```powershell
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'
```

**Add SSH route in Cloudflare Tunnel** (`one.dash.cloudflare.com` → Networks → Connectors → `travelbot` → Routes):

| Field | Value |
|-------|-------|
| Subdomain / Hostname | `ssh` |
| Domain | `sundita.online` |
| Service | `SSH` → `localhost:22` |

Result: `ssh.sundita.online` routes to SSH on the server.

**NOTE:** No Cloudflare Access Application was configured for `ssh.sundita.online` during this session. The tunnel route is added, but anyone who can reach the tunnel could attempt SSH. Access policy should be added as a follow-up.

**Create `deploy` user (non-admin):**

```powershell
net user deploy StrongPass123! /add
```

This user is NOT an administrator — just a plain Windows user.

**Previous user `travelbot` (was admin) — deleted:**

```powershell
net user travelbot /delete
```

---

### Step 2: SSH Config (Client)

File: `C:\Users\AUTHOR\.ssh\config`

```
Host sundita-office
  HostName ssh.sundita.online
  User deploy
  IdentityFile C:\Users\AUTHOR\.ssh\id_ed25519_travelbot
  ProxyCommand cloudflared access ssh --hostname %h
```

---

### Step 3: Authentication — Public Key Setup

**Key on client:**

```
~\.ssh\id_ed25519_travelbot         (private)
~\.ssh\id_ed25519_travelbot.pub     (public)
```

**Key placement on server (via Chrome Remote Desktop):**

Public key was placed in multiple locations during debugging:

1. **Correct location** — `C:\Users\deploy.SST\.ssh\authorized_keys`
2. **Wrong location (doesn't exist)** — `C:\Users\deploy\.ssh\authorized_keys` (the actual profile folder is `deploy.SST`, not `deploy`)
3. **Previously (when user was admin, now irrelevant)** — `C:\ProgramData\ssh\administrators_authorized_keys`

**File permissions verified with `icacls`:**

```
C:\Users\deploy.SST\.ssh\authorized_keys
  NT AUTHORITY\СИСТЕМА:(F)
  SST\deploy:(R)
```

These permissions are correct — only SYSTEM (F) and the user (R). Windows SSH is picky: if `authorized_keys` has inheritable permissions or extra users, it silently ignores the file.

**Result:** SSH connects but **always asks for password**. Public key auth does NOT work despite correct file and permissions.

---

### Step 4: SSH Server Config Debug

File: `C:\ProgramData\ssh\sshd_config`

Enabled key settings:

```
PubkeyAuthentication yes
AuthorizedKeysFile  .ssh/authorized_keys
```

**Critical finding:** There is a SECOND line `AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys` that appears as a default. The config parser uses the **last** `AuthorizedKeysFile` definition. But the line was preceded with `#` (commented), so it should not be active. Verified that `.ssh/authorized_keys` is the active setting.

**Also checked:** `#PubkeyAuthentication yes` — the `#` means this line is COMMENTED. However, the actual config shows `PubkeyAuthentication yes` (uncommented) as the active value. The `#` prefix in the notes above referred to a duplicate commented-out line.

**Despite correct config, public key auth still fails.** Possible causes:
- Windows SSH permission requirements for `authorized_keys` (strict ownership — only the user and SYSTEM)
- SELinux-equivalent? (Windows doesn't have SELinux, but SSH on Windows applies NTFS ACL checks)
- The `deploy` user's home directory path (`C:\Users\deploy.SST\`) is non-standard due to the computer name `SST` being appended to the profile

---

### Step 5: Git Setup on Server

Git was previously installed but not in PATH for `deploy` user. Reinstalled to ensure proper PATH:

Installed Git for Windows to `C:\Program Files\Git` (default location).

**Fix ownership error (`detected dubious ownership in repository`):**

```powershell
git config --global --add safe.directory C:/travel-agent-bot
```

**Fix lock file issue:**

Had to delete `.git\index` due to a lock issue (likely from a previous interrupted operation).

**Verification:**

```powershell
ssh sundita-office "cd C:\travel-agent-bot && git status"
```

Now git works from `deploy` user.

---

### Step 6: Bot Restart Mechanism

**File: `C:\travel-agent-bot\restart-bot.cmd`**

```cmd
@echo off
taskkill /f /im uvicorn.exe 2>nul
timeout /t 2 /nobreak >nul
wscript.exe "C:\travel-agent-bot\start-bot.vbs"
```

This kills the existing uvicorn, waits 2 seconds, then launches the VBS script (which runs uvicorn headless).

**Scheduled Task `RestartTravelBot`:**

```powershell
schtasks /create /tn "RestartTravelBot" ^
  /tr "C:\travel-agent-bot\restart-bot.cmd" ^
  /sc once /st 00:00 /ru "SYSTEM" ^
  /rl highest /f
```

| Parameter | Value |
|-----------|-------|
| Task name | `RestartTravelBot` |
| Trigger | `once` at `00:00` (placeholder — run manually via `/run`) |
| Run as | `SYSTEM` |
| Run level | `highest` (elevated) |
| Created | Yes — visible in `schtasks /query` |

**Note:** `/ST 00:00` was before current time at creation, producing a warning (expected when creating tasks with `/sc once` for manual triggering).

**Result:** Task exists, admin can run it, but `deploy` cannot trigger it.

---

## REMAINING BLOCKER — schtasks Access Denied

### Symptom

```powershell
# As deploy user:
schtasks /run /tn RestartTravelBot
```

Output:

```
ОШИБКА: Отказано в доступе.
```

Translation: `ERROR: Access denied.`

### Attempted Fixes (all failed on Russian Windows)

**1. `icacls` on task file (`C:\Windows\System32\Tasks\RestartTravelBot`):**

```powershell
icacls C:\Windows\System32\Tasks\RestartTravelBot /grant Everyone:RX
```

Error: `Сопоставление между именами пользователей и идентификаторами безопасности не было произведено`

Translation: `No mapping between account names and security IDs was done`

**2. Using SID directly:**

```powershell
icacls C:\Windows\System32\Tasks\RestartTravelBot /grant *S-1-1-0:RX
```

Result: No explicit error but still access denied when running the task.

**3. Using BUILTIN\Users group:**

```powershell
icacls C:\Windows\System32\Tasks\RestartTravelBot /grant BUILTIN\Users:RX
```

Error: Same name mapping failure.

**4. Using BUILTIN\Users SID:**

```powershell
icacls C:\Windows\System32\Tasks\RestartTravelBot /grant *S-1-5-32-545:RX
```

Result: Still access denied.

**5. Direct PowerShell ACL manipulation:**

Attempted `Get-Acl` / `Set-Acl` on `C:\Windows\System32\Tasks\RestartTravelBot` — access denied even reading the ACL.

### Root Cause Analysis

On Russian Windows, the `icacls` name resolution fails because:
- The account names contain Russian characters (e.g., `Администратор`, `Бухгалтер 3`)
- The domain/workgroup name lookup doesn't resolve `BUILTIN\Users` or `Everyone` properly
- Task files are protected — even `deploy` (non-admin) cannot read the ACL to modify it

The task was created with `/ru "SYSTEM" /rl highest`, meaning it runs as SYSTEM with highest privileges. For `deploy` to trigger it, the task's DACL must grant `deploy` the `TASK_EXECUTE` access right on the task file.

**Critical observation:** The task file at `C:\Windows\System32\Tasks\RestartTravelBot` inherits permissions from the `Tasks` folder. On a Russian Windows, the inherited permissions may use localized group names that don't resolve correctly with English SID lookups.

### What Needs to Happen

The `deploy` user needs `TASK_EXECUTE` permission on the task `RestartTravelBot`. This CAN be done from an **admin PowerShell** session by:

1. **Using `schtasks /change` with the `/ru` parameter** — but this changes the run-as user, not who can trigger it.

2. **Using `wevtutil` or `schtasks /security`** — these require specific syntax on Russian Windows.

3. **Using `Get-ScheduledTask` / `Set-ScheduledTask` PowerShell cmdlets** — these may work with SID-based principals instead of names:

   ```powershell
   # From admin PowerShell on the server:
   $task = Get-ScheduledTask -TaskName "RestartTravelBot"
   $task.Principal.LogonType = "ServiceAccount"
   # Or add an access control entry using:
   $task.Principal.Id = "S-1-5-32-545"  # BUILTIN\Users
   Set-ScheduledTask -TaskName "RestartTravelBot" -Principal $task.Principal
   ```

   But the real issue is the DACL on the task, not the principal. The `Get-ScheduledTask` cmdlet in PowerShell 5.1 (Windows Server/Windows client) may not expose the DACL.

4. **Using `schtasks /change /tn RestartTravelBot /ru "SYSTEM" /rp ""`** — just changing run-as won't help.

5. **Alternative approach: Convert to a service instead of scheduled task.** If the bot restart were a Windows service (managed by `sc.exe` or `nssm`), then `deploy` could use `net stop / net start` instead, which can be permission-granted.

6. **Alternative: Create a scheduled task with `/it` (interactive) flag** that runs as the `deploy` user, or use a different trigger mechanism.

**The most promising approach:** Add a DACL entry using the `SCHTASKS.EXE /CHANGE /TN RestartTravelBot /RU SYSTEM` with proper SID-based permission, or use the PowerShell `Set-ScheduledTask` cmdlet from an **admin** session to add `deploy` to the task's security descriptor.

### deploy.ps1 Impact

The deploy script at `D:\projects\travel-agent-bot\deploy.ps1` line 71:

```powershell
ssh $SSH_HOST "schtasks /run /tn RestartTravelBot"
```

This will fail until the permission issue is resolved. The deploy script cannot fully automate deployment without a working restart mechanism.

---

## Key Files

| File | Purpose |
|------|---------|
| `D:\projects\travel-agent-bot\deploy.ps1` | Deploy script — commit → push → ssh → git pull → pip install → tests → restart → health |
| `D:\projects\travel-agent-bot\docs\SSH-REMOTE-ACCESS-SETUP.md` | SSH setup guide (needs update after resolving blocker) |
| `D:\projects\travel-agent-bot\docs\DEPLOY-WINDOWS.md` | Windows deploy docs |
| `C:\Users\AUTHOR\.ssh\config` | SSH client config |
| `C:\Users\AUTHOR\.ssh\id_ed25519_travelbot` | SSH private key |
| `C:\Users\AUTHOR\.ssh\id_ed25519_travelbot.pub` | SSH public key |
| `C:\ProgramData\ssh\sshd_config` | SSH server config |
| `C:\Users\deploy.SST\.ssh\authorized_keys` | Authorized keys (correct location) |
| `C:\travel-agent-bot\restart-bot.cmd` | Bot restart batch script |
| `C:\travel-agent-bot\start-bot.vbs` | Bot start VBS script |
| `C:\Windows\System32\Tasks\RestartTravelBot` | Scheduled task file (the ACL on this file is the crux of the blocker) |

---

## Follow-up Diagnosis (2026-07-07)

Connected via `ssh sundita-office` (already working, see below) and investigated live.

### Issue 2 RESOLVED — pubkey auth works now

`ssh -v sundita-office "echo SSH_OK"` shows:

```
debug1: Offering public key: C:\Users\AUTHOR\.ssh\id_ed25519_travelbot ED25519 ...
debug1: Server accepts key: ...
Authenticated to ssh.sundita.online (via proxy) using "publickey".
```

No password prompt. Whatever was wrong on 07-06 is no longer reproducing — possibly the `authorized_keys` file needed a beat to take effect, or a leftover stale `known_hosts`/session was the issue. **No action needed**, but keep an eye out in case it regresses.

### Issue 1 (BLOCKER) — root cause found

Confirmed on server (as `deploy`):

```
> whoami /groups
...
BUILTIN\Пользователи   ...   S-1-5-32-545   ...
```

`deploy` IS a member of `BUILTIN\Users`. And:

```
> icacls C:\Windows\System32\Tasks\RestartTravelBot
C:\Windows\System32\Tasks\RestartTravelBot BUILTIN\Пользователи:(RX)
                                            NT AUTHORITY\Система:(R)
                                            ...
```

**The NTFS ACL on the task file already grants `BUILTIN\Users` (RX) — and `deploy` is in that group.** So the file-level permissions the previous session spent so much time on were never the problem. `icacls` only edits the NTFS ACL of the file on disk.

The actual blocker: **Task Scheduler keeps its own internal security descriptor, independent of the NTFS ACL**, checked via the Task Scheduler RPC/COM API (`ITaskFolder`/`ITaskDefinition`), not by the filesystem. Confirmed by trying to even *read* it as `deploy`:

```powershell
$s = New-Object -ComObject Schedule.Service; $s.Connect()
$t = $s.GetFolder("\").GetTask("RestartTravelBot")
$t.GetSecurityDescriptor(0xF)
# → Exception calling "GetSecurityDescriptor": "Отказано в доступе. (Исключение из HRESULT: 0x80070005 (E_ACCESSDENIED))"
```

`deploy` can't even read the task's security descriptor, let alone execute it — this is why every `icacls`-based approach in the original session failed silently or with name-mapping errors: they were all editing the wrong ACL.

`deploy`'s SID (for reference, resolved via `whoami /user` and cross-checked with `NTAccount.Translate`):

```
S-1-5-21-3951979689-894011395-14104924-1014
```

### The Fix (drafted, NOT YET RUN — needs admin/elevated session)

Must be run from an elevated PowerShell as `Администратор` (e.g. via Chrome Remote Desktop). This appends an ACE directly to the task's internal security descriptor granting `deploy` Generic Read + Generic Execute (`GRGX`), addressed by SID so it's immune to the Russian-locale name-resolution issues that broke `icacls Everyone` / `icacls BUILTIN\Users`:

```powershell
$deploySid = "S-1-5-21-3951979689-894011395-14104924-1014"  # deploy user, verified above

$scheduler = New-Object -ComObject "Schedule.Service"
$scheduler.Connect()
$task = $scheduler.GetFolder("\").GetTask("RestartTravelBot")

$sd = $task.GetSecurityDescriptor(0xF)
Write-Host "Current SD: $sd"

$sd = $sd + "(A;;GRGX;;;$deploySid)"
$task.SetSecurityDescriptor($sd, 0)

Write-Host "New SD: $($task.GetSecurityDescriptor(0xF))"
```

**Verify from the client (as `deploy`, over SSH) after applying:**

```powershell
ssh sundita-office "schtasks /run /tn RestartTravelBot"
ssh sundita-office "schtasks /query /tn RestartTravelBot"   # check LastRunTime / LastResult
```

**If `SetSecurityDescriptor` itself throws access-denied** (seen on some Windows builds even for admins, per community reports — see reference below), fallback options in priority order:
1. Run the same script from an elevated PowerShell launched via `psexec -s -h powershell.exe` (runs as SYSTEM, bypasses the ownership check).
2. Skip Task Scheduler entirely — convert `RestartTravelBot` into an NSSM-managed Windows service instead, then grant `deploy` service control rights with `sc sdset` (SDDL for services isn't subject to the same Russian-locale `icacls` name-mapping bug since `sc sdset` takes raw SDDL strings, no name lookups involved). This was Issue 1's alternative #3 in the original session notes and is a clean escape hatch if the SD route keeps failing.

**Reference:** [michlstechblog.info — Windows: Permit a limited user to run a scheduled task defined by an Administrator](https://michlstechblog.info/blog/windows-run-task-scheduler-task-as-limited-user/) — this is where the `GRGX` / SDDL-append approach above comes from. The article also flags that `SetSecurityDescriptor` can fail with an ownership-related error on some Server builds — that's the fallback-#1 case above.

---

## Open Issues for the Next AI

### Issue 1 (BLOCKER): `deploy` can't run `schtasks /run /tn RestartTravelBot`

- Task created as SYSTEM, highest privileges
- `deploy` user needs `TASK_EXECUTE` permission on the task file
- `icacls` fails on Russian Windows (name mapping broken for `Everyone`, `BUILTIN\Users`)
- SID-based `icacls` (`*S-1-1-0`, `*S-1-5-32-545`) also fails with access denied
- Need to find the correct Russian Windows incantation, or use an alternative method

**Suggested approaches to try:**
1. From admin PowerShell: `schtasks /change /tn RestartTravelBot /ru "SST\deploy"` (change run-as user)
2. From admin: use `wevtutil` or PowerShell `Register-ScheduledTask` with a properly constructed security descriptor (SDDL)
3. Switch from scheduled task to a Windows service (`nssm` or `sc create`) that `deploy` can `net start`/`net stop`
4. Create a helper service or pipe that allows `deploy` to signal a restart through a safer mechanism
5. Install `subinacl` or `PsExec` to set task permissions
6. Grant `deploy` `SeIncreaseQuotaPrivilege` and `SeServiceLogonRight` via Local Security Policy and try running the restart directly (not through schtasks)

### Issue 2: Public key auth still requires password

- `authorized_keys` is in the right place with correct permissions
- `sshd_config` has `PubkeyAuthentication yes`
- But SSH always prompts for password
- Needs deeper Windows SSH debugging (event log, sshd debug mode)

### Issue 3: No Cloudflare Access Application for SSH

- `ssh.sundita.online` route exists in tunnel but no Access policy
- Anyone who discovers the hostname/route can attempt SSH
- Should add a Self-hosted Access Application for `ssh.sundita.online` with email-based auth

---

## Commands Reference

```powershell
# Connect from client
ssh sundita-office

# Test connection
ssh sundita-office "echo SSH_OK"

# Git pull on server
ssh sundita-office "cd C:\travel-agent-bot && git pull origin master"

# Bot restart attempt (fails for deploy)
ssh sundita-office "schtasks /run /tn RestartTravelBot"

# View scheduled tasks
ssh sundita-office "schtasks /query /tn RestartTravelBot"

# Check sshd config
ssh sundita-office "type C:\ProgramData\ssh\sshd_config | findstr Pubkey"

# Check authorized_keys permissions
ssh sundita-office "icacls C:\Users\deploy.SST\.ssh\authorized_keys"
```
