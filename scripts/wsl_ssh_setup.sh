#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  scripts/wsl_ssh_setup.sh
#  Run this ONCE on your WSL machine to enable SSH for CI/CD deploys.
#  Usage:  bash scripts/wsl_ssh_setup.sh
# ═══════════════════════════════════════════════════════════════════

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
BOLD='\033[1m'

echo ""
echo -e "${CYAN}${BOLD}  ⚡ Bolt — WSL SSH Setup for CI/CD${NC}"
echo -e "  ──────────────────────────────────────"
echo ""

# ── Step 1: Install OpenSSH Server ────────────────────────────────
echo -e "${BOLD}[1/5] Installing OpenSSH Server...${NC}"
sudo apt-get update -qq
sudo apt-get install -y openssh-server
echo -e "  ${GREEN}✔ OpenSSH installed${NC}"

# ── Step 2: Configure SSHD ────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/5] Configuring SSH daemon...${NC}"

# Backup existing config
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak 2>/dev/null || true

# Write a clean, working sshd_config for WSL
sudo tee /etc/ssh/sshd_config > /dev/null <<'EOF'
# Bolt CI/CD — WSL SSH Configuration
Port 22
ListenAddress 0.0.0.0

# Authentication
PermitRootLogin no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PasswordAuthentication no
ChallengeResponseAuthentication no

# Keep-alive
ClientAliveInterval 60
ClientAliveCountMax 3

# WSL compatibility
UsePAM yes
PrintMotd no
AcceptEnv LANG LC_*
Subsystem sftp /usr/lib/openssh/sftp-server
EOF

echo -e "  ${GREEN}✔ sshd_config written${NC}"

# ── Step 3: Generate deploy key pair ──────────────────────────────
echo ""
echo -e "${BOLD}[3/5] Generating deploy SSH key pair...${NC}"

KEY_DIR="$HOME/.ssh"
DEPLOY_KEY="$KEY_DIR/bolt_deploy"

mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"

if [ -f "$DEPLOY_KEY" ]; then
  echo -e "  ${YELLOW}⚠  Deploy key already exists at $DEPLOY_KEY — skipping generation${NC}"
  echo -e "     Delete it and re-run to regenerate."
else
  ssh-keygen -t ed25519 -f "$DEPLOY_KEY" -N "" -C "bolt-github-actions-deploy" -q
  echo -e "  ${GREEN}✔ Key pair generated: $DEPLOY_KEY (private) and $DEPLOY_KEY.pub (public)${NC}"
fi

# Add public key to authorized_keys
cat "$DEPLOY_KEY.pub" >> "$KEY_DIR/authorized_keys"
sort -u "$KEY_DIR/authorized_keys" -o "$KEY_DIR/authorized_keys"
chmod 600 "$KEY_DIR/authorized_keys"
echo -e "  ${GREEN}✔ Public key added to authorized_keys${NC}"

# ── Step 4: Start SSH service ──────────────────────────────────────
echo ""
echo -e "${BOLD}[4/5] Starting SSH service...${NC}"

sudo service ssh start
sudo service ssh status | head -3

echo -e "  ${GREEN}✔ SSH service started${NC}"

# ── Step 5: Print secrets for GitHub ──────────────────────────────
echo ""
echo -e "${BOLD}[5/5] GitHub Secrets you need to add${NC}"
echo -e "  Go to: ${CYAN}https://github.com/Ayush-io-code/Bolt_ansible/settings/secrets/actions${NC}"
echo ""

WSL_IP=$(hostname -I | awk '{print $1}')

echo -e "  ${YELLOW}┌─────────────────────────────────────────────────────────┐${NC}"
echo -e "  ${YELLOW}│  Secret Name          │  Value                          │${NC}"
echo -e "  ${YELLOW}├─────────────────────────────────────────────────────────┤${NC}"
echo -e "  ${YELLOW}│  WSL_HOST             │  $WSL_IP                        │${NC}"
echo -e "  ${YELLOW}│  WSL_SSH_PRIVATE_KEY  │  (see below — full key)         │${NC}"
echo -e "  ${YELLOW}│  GHCR_PAT             │  (your GitHub PAT — see note)   │${NC}"
echo -e "  ${YELLOW}└─────────────────────────────────────────────────────────┘${NC}"
echo ""

echo -e "${BOLD}  WSL_SSH_PRIVATE_KEY — copy everything below:${NC}"
echo -e "  ${RED}─────────────────────────────────────────────────${NC}"
cat "$DEPLOY_KEY"
echo -e "  ${RED}─────────────────────────────────────────────────${NC}"

echo ""
echo -e "${BOLD}  GHCR_PAT — create a Personal Access Token:${NC}"
echo -e "  1. Go to https://github.com/settings/tokens/new"
echo -e "  2. Note: 'Bolt GHCR Deploy'"
echo -e "  3. Expiration: 90 days (or No expiration)"
echo -e "  4. Scopes: check ${CYAN}write:packages${NC} and ${CYAN}read:packages${NC}"
echo -e "  5. Copy the token and add it as GHCR_PAT secret"

echo ""
echo -e "${GREEN}${BOLD}  ✅ WSL SSH setup complete!${NC}"
echo ""
echo -e "  ${YELLOW}⚠  WSL IMPORTANT NOTE:${NC}"
echo -e "  WSL resets on each Windows reboot. Add this to your Windows"
echo -e "  Task Scheduler or ~/.bashrc to auto-start SSH:"
echo -e "  ${CYAN}  sudo service ssh start${NC}"
echo ""

# ── Auto-start hint for .bashrc ───────────────────────────────────
if ! grep -q "service ssh start" ~/.bashrc 2>/dev/null; then
  echo ""
  read -p "  Auto-add 'sudo service ssh start' to ~/.bashrc? [y/N]: " ADD_TO_BASHRC
  if [[ "$ADD_TO_BASHRC" =~ ^[Yy]$ ]]; then
    echo "" >> ~/.bashrc
    echo "# Auto-start SSH for Bolt CI/CD" >> ~/.bashrc
    echo "sudo service ssh start > /dev/null 2>&1 || true" >> ~/.bashrc
    echo -e "  ${GREEN}✔ Added to ~/.bashrc${NC}"
  fi
fi
