#!/usr/bin/env bash
# Выкладка учебного стенда «Магазин у дома» : inventory-lab.tsdpu.org → 127.0.0.1:18090.
# Повторный запуск безопасен: файлы перезаписываются, контейнер пересоздаётся, данные (games) сохраняются.
set -euo pipefail
HOST="${DEPLOY_HOST:?Укажите DEPLOY_HOST — ssh-хост с Docker и nginx}"
DIR=/opt/apps/inventory-lab-stand
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30"
cd "$(dirname "$0")"
$SSH $HOST "mkdir -p $DIR/app $DIR/data && chown 1000:1000 $DIR/data"
FILES=$(ls *.py | grep -v "^test_")
"${PYTHON:-python3}" -c "import app"  # все модули должны импортироваться до выкладки
scp -o BatchMode=yes -q $FILES index.html $HOST:$DIR/app/
$SSH $HOST "set -e
docker rm -f inventory-lab-stand >/dev/null 2>&1 || true
docker run -d --name inventory-lab-stand --restart unless-stopped \
  -p 127.0.0.1:18090:8080 --user 1000:1000 --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --memory 96m --cpus 0.5 --pids-limit 64 \
  --log-opt max-size=5m --log-opt max-file=2 \
  -e STAND_DB=/data/stand.db -e PORT=8080 -e PYTHONDONTWRITEBYTECODE=1 \
  -v $DIR/app:/app:ro -v $DIR/data:/data -w /app python:3.12-alpine python app.py
for i in \$(seq 30); do curl -fsS http://127.0.0.1:18090/health && exit 0; sleep 1; done; echo НЕ_ПОДНЯЛСЯ; docker logs --tail 20 inventory-lab-stand; exit 1"

# nginx: заменить заглушку 503 на прокси к стенду (идемпотентно; копия прежнего файла рядом с датой).
$SSH $HOST 'set -e
F=/etc/nginx/sites-available/inventory-lab
if grep -q "not-deployed" $F; then
  cp -p $F /root/inventory-lab.nginx.bak-$(date +%Y%m%d%H%M%S)
  python3 - "$F" <<"PY"
import sys,re
p=sys.argv[1];s=open(p,encoding="utf-8").read()
s=re.sub(r"    location = /health \{[^\n]*\n    location / \{[^\n]*\n",
 "    location / { proxy_pass http://127.0.0.1:18090; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-For $remote_addr; client_max_body_size 16k; proxy_read_timeout 30s; }\n",s)
assert "not-deployed" not in s and "18090" in s
open(p,"w",encoding="utf-8").write(s)
PY
fi
nginx -t 2>&1 | tail -1 && systemctl reload nginx && echo NGINX_OK'
