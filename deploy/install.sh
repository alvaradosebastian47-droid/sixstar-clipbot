#!/usr/bin/env bash
# Instalación en un VPS Ubuntu 22.04/24.04 (Hostinger KVM 2 o similar). Correr como root:
#   git clone <repo> /opt/clipbot && cd /opt/clipbot && bash deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
apt-get update -y
apt-get install -y ffmpeg python3-venv python3-pip fontconfig curl git
# Montserrat ExtraBold para los subtítulos
mkdir -p /usr/share/fonts/truetype/montserrat
curl -fsSL -o /usr/share/fonts/truetype/montserrat/Montserrat-ExtraBold.ttf \
  https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-ExtraBold.ttf
fc-cache -f >/dev/null
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
ln -sf "$(pwd)/.venv/bin/streamlink" /usr/local/bin/streamlink
ln -sf "$(pwd)/.venv/bin/yt-dlp" /usr/local/bin/yt-dlp
[ -f config.yaml ] || cp config.example.yaml config.yaml
mkdir -p /opt/clipbot/work
cp deploy/clipbot.service /etc/systemd/system/clipbot.service
systemctl daemon-reload
echo "Listo. Llena config.yaml y luego:"
echo "  .venv/bin/python -m clipbot.main --once --dry-run   # prueba sin publicar"
echo "  systemctl enable --now clipbot                      # arranca el servicio"
echo "  journalctl -u clipbot -f                            # ver logs"
