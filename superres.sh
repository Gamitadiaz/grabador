#!/usr/bin/env bash
# Atajo: ./superres.sh 1920x1080  |  ./superres.sh off
exec python3 "$(dirname "$(readlink -f "$0")")/grabador.py" superres "${1:-1920x1080}"
