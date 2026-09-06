#!/usr/bin/env bash
set -o errexit
exec python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/login', timeout=3)"
