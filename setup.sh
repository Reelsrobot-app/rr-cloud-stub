#!/bin/bash
# setup.sh — скрипт окружения облака (вставляется в поле Setup script окружения на claude.ai/code).
# Заглушка ReelsRobot: ставит то же, что понадобится движку, но без кода продукта.
# Требования документации: код выхода 0, до ~5 минут (иначе окружение не кешируется),
# переменные окружения здесь ещё не заданы, сетевой секрет в запросы скрипта не подставляется.
set -u
T0=$(date +%s)
mkdir -p /opt/rr-stub
{
  echo "start $(date -u +%FT%TZ)"
  apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg fonts-noto-color-emoji >/dev/null \
    && echo "apt ok $(( $(date +%s) - T0 )) s" || echo "apt FAIL"
  T1=$(date +%s)
  # Ubuntu 24.04: системный pip может отказать (PEP 668, externally-managed) — тогда с флагом
  PKGS="numpy pillow opencv-python-headless fonttools onnxruntime"
  { python3 -m pip install -q --disable-pip-version-check $PKGS \
      || python3 -m pip install -q --disable-pip-version-check --break-system-packages $PKGS; } \
    && echo "pip ok $(( $(date +%s) - T1 )) s" || echo "pip FAIL"
  # Remotion (сцены режиссёра): системные библиотеки Chrome Headless Shell для Ubuntu 24.04 —
  # список из документации Remotion (remotion.dev/docs/miscellaneous/linux-dependencies)
  T2=$(date +%s)
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libnss3 libdbus-1-3 libatk1.0-0 libasound2t64 \
    libxrandr2 libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1 libgbm-dev libcups2 libcairo2 \
    libpango-1.0-0 libatk-bridge2.0-0 >/dev/null && echo "apt chrome-libs ok $(( $(date +%s) - T2 )) s" || echo "apt chrome-libs FAIL"
  echo "node $(node --version 2>/dev/null || echo НЕТ)"
  mkdir -p /opt/rr-stub/remotion && cd /opt/rr-stub/remotion
  cat > package.json <<'PKG'
{"name": "rr-remotion-proba", "private": true,
 "dependencies": {"@remotion/cli": "4.0.529", "react": "19.3.0", "react-dom": "19.3.0", "remotion": "4.0.529"}}
PKG
  T3=$(date +%s)
  npm install --no-audit --no-fund --loglevel=error >/dev/null 2>&1 && echo "npm ok $(( $(date +%s) - T3 )) s" || echo "npm FAIL"
  T4=$(date +%s)
  # браузер: Remotion 4.0.529 на glibc ≥ 2.35 качает его с remotion.media (адрес — в список окружения)
  npx --no-install remotion browser ensure >/dev/null 2>&1 && echo "browser ok $(( $(date +%s) - T4 )) s" || echo "browser FAIL (remotion.media не в списке окружения?)"
  du -sm /opt/rr-stub/remotion/node_modules 2>/dev/null | sed 's/^/node_modules MB: /'
  cd /
  echo "total $(( $(date +%s) - T0 )) s"
  date -u +%FT%TZ > /opt/rr-stub/setup-stamp
} > /opt/rr-stub/setup.log 2>&1
exit 0
