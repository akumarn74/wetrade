#!/usr/bin/env bash
# Droplet-friendly install: keep grpcio/grpcio-tools on wheels; constrain full resolve.
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

python -m pip install -U "pip>=24.2" "setuptools>=70,<81" wheel

# Prefer wheels; Webull pins grpcio 1.51.1. Py3.12 may need compile (add 4G+ swap + build-essential).
if ! python -m pip install --only-binary=:all: -c backend/constraints-grpc.txt \
  "grpcio==1.51.1" "grpcio-tools==1.51.1" 2>/dev/null; then
  echo "No grpc wheels for this platform; compiling (needs RAM/swap + g++) ..." >&2
  python -m pip install --no-build-isolation -c backend/constraints-grpc.txt \
    "grpcio==1.51.1" "grpcio-tools==1.51.1"
fi

# One resolve for the rest; constraints prevent grpc from being upgraded/rebuilt.
python -m pip install --no-build-isolation -c backend/constraints-grpc.txt -r backend/requirements.txt

python -c "import grpc; import grpc_tools; print('OK grpc', grpc.__version__)"
