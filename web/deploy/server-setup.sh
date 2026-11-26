#!/usr/bin/env bash
# One-time Ubuntu/Debian server prep for the IT Provisioning web server.
# Run as root (or with sudo):  sudo bash server-setup.sh
# Safe to re-run.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

. /etc/os-release
echo "==> OS: $PRETTY_NAME"
case "$ID" in
  ubuntu|debian) ;;
  *) echo "Unsupported OS: $ID (need ubuntu or debian)" >&2; exit 1 ;;
esac

echo "==> Updating packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg ufw fail2ban unattended-upgrades git

echo "==> Installing Docker (official repo)"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

echo "==> Firewall: allow SSH, HTTP, HTTPS only"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> fail2ban (SSH brute-force protection)"
systemctl enable --now fail2ban

echo "==> Automatic security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable --now unattended-upgrades

echo "==> App directory"
mkdir -p /opt/itops
chmod 750 /opt/itops

echo
echo "================ DONE ================"
docker --version
docker compose version
ufw status verbose
echo
echo "Next: once SSH key login works, disable password login:"
echo "  set 'PasswordAuthentication no' in /etc/ssh/sshd_config, then: systemctl restart ssh"
