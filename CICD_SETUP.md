# ⚡ Bolt — CI/CD Pipeline Setup Guide

Complete guide to wire up GitHub Actions CI/CD for the Bolt Ansible platform,
deploying automatically to your WSL machine on every push to `main`.

---

## Pipeline Overview

```
Push to main
     │
     ▼
┌─────────────┐     ┌──────────────────┐
│ test-backend │     │  test-frontend   │
│  - flake8   │     │  - HTML check    │
│  - smoke    │     │  - nginx -t      │
└──────┬──────┘     └────────┬─────────┘
       └────────┬────────────┘
                ▼
     ┌──────────────────────┐
     │   build-and-push     │
     │  - Build backend img │
     │  - Build frontend img│
     │  - Push → GHCR       │
     └──────────┬───────────┘
                ▼
     ┌──────────────────────┐
     │       deploy         │
     │  - SSH into WSL      │
     │  - Pull new images   │
     │  - docker compose up │
     │  - Health check      │
     └──────────────────────┘
```

**PRs** only run the two test jobs (no build/push/deploy).
**Pushes to main** run the full pipeline.

---

## Step 1 — Copy files into your project

Copy these files into your `bolt_new` project root:

```
bolt_new/
├── .github/
│   └── workflows/
│       └── cicd.yml              ← GitHub Actions workflow
├── docker-compose.prod.yml       ← Production image override
└── scripts/
    └── wsl_ssh_setup.sh          ← Run once on WSL
```

---

## Step 2 — Set up SSH on WSL

SSH isn't running on your machine yet. Run the setup script in WSL:

```bash
cd /mnt/c/Projects/bolt_v12/bolt_new
bash scripts/wsl_ssh_setup.sh
```

The script will:
1. Install `openssh-server`
2. Configure `/etc/ssh/sshd_config` (key-auth only, no passwords)
3. Generate a deploy key pair (`~/.ssh/bolt_deploy`)
4. Add the public key to `authorized_keys`
5. Start the SSH service
6. Print the exact values you need for GitHub Secrets

---

## Step 3 — Add GitHub Secrets

Go to: **https://github.com/Ayush-io-code/Bolt_ansible/settings/secrets/actions**

Add these three secrets:

| Secret Name           | Value                                              |
|-----------------------|----------------------------------------------------|
| `WSL_HOST`            | Your WSL IP — output of `hostname -I` → `172.25.75.26` (but re-check after reboots — see note below) |
| `WSL_SSH_PRIVATE_KEY` | Full content of `~/.ssh/bolt_deploy` (printed by setup script) |
| `GHCR_PAT`            | GitHub Personal Access Token with `write:packages` + `read:packages` |

### Creating the GHCR_PAT:
1. Go to https://github.com/settings/tokens/new
2. Note: `Bolt GHCR Deploy`
3. Expiration: 90 days
4. Check scopes: **`write:packages`** and **`read:packages`**
5. Click **Generate token** → copy it → add as `GHCR_PAT` secret

---

## Step 4 — Push to trigger the pipeline

```bash
cd /mnt/c/Projects/bolt_v12/bolt_new
git add .github/ docker-compose.prod.yml scripts/
git commit -m "ci: add GitHub Actions CI/CD pipeline"
git push origin main
```

Then watch it run at:
**https://github.com/Ayush-io-code/Bolt_ansible/actions**

---

## ⚠️ WSL-Specific Notes

### Dynamic IP problem
WSL gets a new IP on every Windows reboot. `172.25.75.26` is your current IP
but it **will change**. You have two options:

**Option A — Update the secret after each reboot (simple)**
```bash
# After rebooting, run this in WSL and update WSL_HOST secret:
hostname -I
```

**Option B — Set a static WSL IP (permanent fix)**
Create/edit `C:\Users\<your-windows-user>\.wslconfig`:
```ini
[wsl2]
# Forces WSL to use a specific subnet so the IP stays consistent
networkingMode=mirrored
```
Then restart WSL: `wsl --shutdown` → reopen terminal.
With `networkingMode=mirrored`, WSL uses your Windows IP directly.

### SSH auto-start after reboot
WSL doesn't auto-start services. The setup script offers to add this to
`~/.bashrc`, but you can also do it manually:

```bash
echo "sudo service ssh start > /dev/null 2>&1 || true" >> ~/.bashrc
```

Or create a Windows Task Scheduler job to run `wsl sudo service ssh start`
on Windows login.

---

## Verify Everything Works

### Test SSH from outside WSL (from Windows PowerShell):
```powershell
ssh -i \\wsl$\Ubuntu\home\ayush\.ssh\bolt_deploy ayush@172.25.75.26
```

### Test Docker login to GHCR:
```bash
echo YOUR_GHCR_PAT | docker login ghcr.io -u ayush-io-code --password-stdin
```

### Manually trigger the pipeline:
```bash
git commit --allow-empty -m "ci: trigger test deploy"
git push origin main
```

---

## Secrets Checklist

- [ ] `WSL_HOST` — added (current WSL IP)
- [ ] `WSL_SSH_PRIVATE_KEY` — added (private key from setup script)
- [ ] `GHCR_PAT` — added (GitHub PAT with packages scope)

## Files Checklist

- [ ] `.github/workflows/cicd.yml` — committed
- [ ] `docker-compose.prod.yml` — committed
- [ ] `scripts/wsl_ssh_setup.sh` — committed

---

## Troubleshooting

**Build fails at `test-backend` / smoke test**
→ Check `backend/requirements.txt` includes `flask` and `pyyaml`

**`docker login ghcr.io` fails in deploy step**
→ GHCR_PAT might be expired or missing `write:packages` scope — regenerate it

**SSH connection refused**
→ SSH not running: `sudo service ssh start` in WSL
→ Wrong IP: re-check `hostname -I` and update `WSL_HOST` secret

**SSH permission denied**
→ Key mismatch: re-run `scripts/wsl_ssh_setup.sh` and update `WSL_SSH_PRIVATE_KEY` secret

**docker-compose.prod.yml `!reset` error**
→ Your Docker Compose version is older than v2.x — upgrade:
  `sudo apt-get install docker-compose-plugin`
