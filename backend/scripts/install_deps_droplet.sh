#!/usr/bin/env bash
# Droplet-friendly install: use *prebuilt* grpcio wheels (Webull pins grpcio==1.51.1).
# Usage (repo root, venv on):
#   cd /root/wetrade && source .venv-prod311/bin/activate && bash backend/scripts/install_deps_droplet.sh
set -euo pipefail

# Script lives at backend/scripts/ — repo root is two levels up.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "Activate your venv first: source .venv-prod311/bin/activate" >&2
  exit 1
fi

maj=$(python -c "import sys; print(sys.version_info.major)")
min=$(python -c "import sys; print(sys.version_info.minor)")
if (( maj == 3 && min >= 12 )); then
  echo "ERROR: This venv is Python ${maj}.${min}." >&2
  echo "Webull's dependency grpcio==1.51.1 has no practical manylinux wheel for Python 3.12 — pip compiles for ~10+ minutes and often fails on small VPSs." >&2
  echo "Fix: recreate the venv with Python 3.10 (recommended) or 3.11:" >&2
  echo "  sudo apt update && sudo apt install -y python3.10 python3.10-venv python3.10-dev build-essential" >&2
  echo "  cd $ROOT && rm -rf .venv-prod311 && python3.10 -m venv .venv-prod311 && source .venv-prod311/bin/activate" >&2
  echo "  bash backend/scripts/install_deps_droplet.sh" >&2
  exit 1
fi

python -m pip install -U "pip>=24.2" "setuptools>=70,<81" wheel

echo "Installing grpcio 1.51.1 (wheels only) ..."
python -m pip install --only-binary=:all: -c backend/constraints-grpc.txt \
  "grpcio==1.51.1" "grpcio-tools==1.51.1"

echo "Installing remaining requirements ..."
python -m pip install --no-build-isolation -c backend/constraints-grpc.txt -r backend/requirements.txt

python -c "import grpc; import grpc_tools; print('OK grpc', grpc.__version__)"
