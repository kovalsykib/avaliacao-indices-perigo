#!/usr/bin/env bash
# Monta a pasta _site publicada no GitHub Pages:
#   /            calculadora (app/index.html + worker.js)
#   /codigo/     programa em Python usado pela calculadora
#   /resultados/ últimos resultados gerados pelo GitHub Actions (se houver)
set -euo pipefail
DEST="${1:-_site}"
RES="${2:-}"
rm -rf "$DEST"
mkdir -p "$DEST/codigo/src" "$DEST/codigo/exemplo"
cp app/index.html app/worker.js "$DEST/"
cp rodar.py "$DEST/codigo/"
cp src/*.py "$DEST/codigo/src/"
cp exemplo/gerar_dados_exemplo.py "$DEST/codigo/exemplo/"
if [ -n "$RES" ] && [ -f "$RES/index.html" ]; then
  mkdir -p "$DEST/resultados"
  cp -r "$RES"/. "$DEST/resultados/"
fi
touch "$DEST/.nojekyll"
echo "Site montado em $DEST"
