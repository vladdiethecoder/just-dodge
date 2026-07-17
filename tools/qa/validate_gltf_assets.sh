#!/usr/bin/env bash
# Fail-closed Khronos glTF validation gate for all tracked GLB assets (JD-RC0 §2).
# Validates every tracked *.glb with the official Khronos gltf-validator and fails
# if any asset reports a validation error. Uses an isolated npm prefix so no global
# install is required.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
PREFIX="${GLTF_VALIDATOR_PREFIX:-/tmp/jd_gltf_validator}"
PKG="gltf-validator@2.0.0-dev.3.10"

if ! command -v node >/dev/null 2>&1; then
    echo "GLTF_VALIDATION=SKIP node unavailable" >&2
    exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
    echo "GLTF_VALIDATION=SKIP npm unavailable" >&2
    exit 1
fi

if [[ ! -f "$PREFIX/lib/node_modules/gltf-validator/index.mjs" && ! -d "$PREFIX/lib/node_modules/gltf-validator" ]]; then
    echo "installing $PKG into isolated prefix $PREFIX" >&2
    NPM_CONFIG_PREFIX="$PREFIX" npm install -g "$PKG" >&2
fi

RUNNER="$PREFIX/run_gltf_validator.cjs"
cat > "$RUNNER" <<'EOF'
const fs = require('fs');
const path = require('path');
const validator = require(process.env.GLTF_VAL_MODULE);
(async () => {
  const file = process.argv[2];
  const buf = fs.readFileSync(file);
  const r = await validator.validateBytes(new Uint8Array(buf));
  const i = r.issues;
  const errs = i.messages.filter(m => m.severity === 0).map(m => m.code + ':' + (m.pointer||''));
  console.log(JSON.stringify({file: path.basename(file), errors: i.numErrors, warnings: i.numWarnings, errCodes: errs.slice(0,5)}));
  process.exit(i.numErrors > 0 ? 1 : 0);
})().catch(e => { console.error('VALIDATOR_ERR', e.message); process.exit(2); });
EOF

export GLTF_VAL_MODULE="$PREFIX/lib/node_modules/gltf-validator"

mapfile -t GLBS < <(git -C "$ROOT" ls-files | grep -i '\.glb$')
if [[ ${#GLBS[@]} -eq 0 ]]; then
    echo "GLTF_VALIDATION=FAIL no tracked GLB assets found" >&2
    exit 1
fi

fail=0
for rel in "${GLBS[@]}"; do
    if ! node "$RUNNER" "$ROOT/$rel"; then
        echo "GLTF_VALIDATION=ERROR $rel" >&2
        fail=1
    fi
done

if [[ $fail -ne 0 ]]; then
    echo "GLTF_VALIDATION=FAIL" >&2
    exit 1
fi
echo "GLTF_VALIDATION=PASS assets=${#GLBS[@]}"
