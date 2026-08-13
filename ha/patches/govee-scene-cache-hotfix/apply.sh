#!/usr/bin/env bash

set -euo pipefail

readonly REMOTE_DIR="/config/custom_components/govee"
readonly EXPECTED_SCENE_SHA256="97c6d34882139d15d0fde015cdd3e3446ab72ece9fb60cbd5d374f23057bb239"
readonly EXPECTED_COORDINATOR_SHA256="0dcdcac416d5677926ac668c5358681fd162f79d52fc6d62e2c75670f13f1e56"
readonly PATCHED_SCENE_SHA256="3a5062cac9a9db32ef429f81d383be9fb18e32a102251100d0dd4781fc2222ae"
readonly PATCHED_COORDINATOR_SHA256="b86fcd076822c1eb5e5a1f45b8e4ce967d35a6338432631291ff9f47cb575210"

usage() {
    printf 'Usage: bash %s (--check|--apply) SSH_TARGET\n' "$0" >&2
}

if [[ $# -ne 2 ]]; then
    usage
    exit 2
fi

readonly MODE="$1"
readonly SSH_TARGET="$2"
if [[ "$MODE" != "--check" && "$MODE" != "--apply" ]]; then
    usage
    exit 2
fi

for required_command in ssh patch mktemp; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        printf 'Required local command not found: %s\n' "$required_command" >&2
        exit 2
    fi
done

PYTHON_BIN=""
for python_candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$python_candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$python_candidate"
        break
    fi
done
if [[ -z "$PYTHON_BIN" ]]; then
    printf 'A local Python 3 interpreter is required for syntax validation.\n' >&2
    exit 2
fi

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly SCENE_OVERLAY="$SCRIPT_DIR/scene_cache.py"
readonly COORDINATOR_PATCH="$SCRIPT_DIR/coordinator.patch"

if [[ "$(sha256_file "$SCENE_OVERLAY")" != "$PATCHED_SCENE_SHA256" ]]; then
    printf 'Refusing: local scene overlay no longer matches PATCHED_SCENE_SHA256.\n' >&2
    exit 4
fi

STAGE_DIR="$(mktemp -d /tmp/govee-scene-hotfix.XXXXXX)"
readonly STAGE_DIR
REMOTE_STAGE=""

cleanup() {
    local exit_code=$?
    trap - EXIT
    if [[ -n "$REMOTE_STAGE" ]]; then
        ssh "$SSH_TARGET" sudo sh -s -- "$REMOTE_STAGE" <<'REMOTE_CLEANUP' >/dev/null 2>&1 || true
stage=$1
case "$stage" in
    /tmp/govee-scene-hotfix.*) rm -rf -- "$stage" ;;
esac
REMOTE_CLEANUP
    fi
    rm -rf -- "$STAGE_DIR"
    exit "$exit_code"
}
trap cleanup EXIT

# Read-only fetch. The exact hashes pin this overlay to the audited v2026.7.8
# files and prevent applying it over local edits or a future integration release.
ssh "$SSH_TARGET" "cat '$REMOTE_DIR/scene_cache.py'" \
    > "$STAGE_DIR/scene_cache.py.original"
ssh "$SSH_TARGET" "cat '$REMOTE_DIR/coordinator.py'" \
    > "$STAGE_DIR/coordinator.py"

actual_scene_sha256="$(sha256_file "$STAGE_DIR/scene_cache.py.original")"
actual_coordinator_sha256="$(sha256_file "$STAGE_DIR/coordinator.py")"

# A repeat check/apply must be a safe no-op. Validate the complete installed
# pair, rather than accepting one patched file mixed with one upstream file.
if [[ "$actual_scene_sha256" == "$PATCHED_SCENE_SHA256" \
    && "$actual_coordinator_sha256" == "$PATCHED_COORDINATOR_SHA256" ]]; then
    "$PYTHON_BIN" -m py_compile \
        "$STAGE_DIR/scene_cache.py.original" \
        "$STAGE_DIR/coordinator.py"
    if [[ "$(grep -c 'async with asyncio.timeout(self._fetch_timeout)' "$STAGE_DIR/scene_cache.py.original")" -ne 2 \
        || "$(grep -c 'await self._scene_cache.async_shutdown()' "$STAGE_DIR/coordinator.py")" -ne 1 ]]; then
        printf 'Refusing: installed Govee hotfix failed structural validation.\n' >&2
        exit 4
    fi
    printf 'Govee scene-cache hotfix is already installed and valid.\n'
    printf '  scene_cache.py  %s\n' "$actual_scene_sha256"
    printf '  coordinator.py %s\n' "$actual_coordinator_sha256"
    printf 'No remote files were changed.\n'
    exit 0
fi

if [[ "$actual_scene_sha256" != "$EXPECTED_SCENE_SHA256" ]]; then
    printf 'Refusing: remote scene_cache.py SHA-256 is %s (expected %s).\n' \
        "$actual_scene_sha256" "$EXPECTED_SCENE_SHA256" >&2
    exit 3
fi
if [[ "$actual_coordinator_sha256" != "$EXPECTED_COORDINATOR_SHA256" ]]; then
    printf 'Refusing: remote coordinator.py SHA-256 is %s (expected %s).\n' \
        "$actual_coordinator_sha256" "$EXPECTED_COORDINATOR_SHA256" >&2
    exit 3
fi

cp "$SCENE_OVERLAY" "$STAGE_DIR/scene_cache.py"
(
    cd "$STAGE_DIR"
    patch -f -s -p0 < "$COORDINATOR_PATCH"
)

# Compile both complete staged modules. This does not import Home Assistant.
"$PYTHON_BIN" -m py_compile \
    "$STAGE_DIR/scene_cache.py" \
    "$STAGE_DIR/coordinator.py"

if [[ "$(grep -c 'async with asyncio.timeout(self._fetch_timeout)' "$STAGE_DIR/scene_cache.py")" -ne 2 ]]; then
    printf 'Refusing: staged scene cache does not contain both deadlines.\n' >&2
    exit 4
fi
if [[ "$(grep -c 'await self._scene_cache.async_shutdown()' "$STAGE_DIR/coordinator.py")" -ne 1 ]]; then
    printf 'Refusing: staged coordinator shutdown hook is missing or duplicated.\n' >&2
    exit 4
fi

patched_scene_sha256="$(sha256_file "$STAGE_DIR/scene_cache.py")"
patched_coordinator_sha256="$(sha256_file "$STAGE_DIR/coordinator.py")"
if [[ "$patched_scene_sha256" != "$PATCHED_SCENE_SHA256" \
    || "$patched_coordinator_sha256" != "$PATCHED_COORDINATOR_SHA256" ]]; then
    printf 'Refusing: staged Govee hotfix no longer matches its audited hashes.\n' >&2
    exit 4
fi

if [[ "$MODE" == "--check" ]]; then
    printf 'CHECK ONLY: compatible Govee source found; staged files compile.\n'
    printf '  scene_cache.py  %s\n' "$patched_scene_sha256"
    printf '  coordinator.py %s\n' "$patched_coordinator_sha256"
    printf 'No remote files were changed.\n'
    exit 0
fi

backup_suffix="pre-scene-hotfix-$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_STAGE="$(ssh "$SSH_TARGET" "mktemp -d '/tmp/govee-scene-hotfix.XXXXXX'")"
case "$REMOTE_STAGE" in
    /tmp/govee-scene-hotfix.*) ;;
    *)
        printf 'Refusing unexpected remote staging path: %s\n' "$REMOTE_STAGE" >&2
        exit 5
        ;;
esac

ssh "$SSH_TARGET" "umask 022; cat > '$REMOTE_STAGE/scene_cache.py'" \
    < "$STAGE_DIR/scene_cache.py"
ssh "$SSH_TARGET" "umask 022; cat > '$REMOTE_STAGE/coordinator.py'" \
    < "$STAGE_DIR/coordinator.py"

# Recheck both originals immediately before commit. Backups remain next to the
# target files. Each rename is atomic; a failure rolls back either replacement.
ssh "$SSH_TARGET" sudo sh -s -- \
    "$REMOTE_STAGE" \
    "$backup_suffix" \
    "$EXPECTED_SCENE_SHA256" \
    "$EXPECTED_COORDINATOR_SHA256" \
    "$patched_scene_sha256" \
    "$patched_coordinator_sha256" <<'REMOTE_APPLY'
set -eu

stage=$1
backup_suffix=$2
expected_scene=$3
expected_coordinator=$4
patched_scene=$5
patched_coordinator=$6
base=/config/custom_components/govee

case "$stage" in
    /tmp/govee-scene-hotfix.*) ;;
    *)
        printf 'Unexpected staging path: %s\n' "$stage" >&2
        exit 5
        ;;
esac

hash_file() {
    sha256sum "$1" | awk '{print $1}'
}

if [ "$(hash_file "$base/scene_cache.py")" != "$expected_scene" ]; then
    printf 'scene_cache.py changed after validation; refusing commit.\n' >&2
    exit 6
fi
if [ "$(hash_file "$base/coordinator.py")" != "$expected_coordinator" ]; then
    printf 'coordinator.py changed after validation; refusing commit.\n' >&2
    exit 6
fi
if [ "$(hash_file "$stage/scene_cache.py")" != "$patched_scene" ]; then
    printf 'Uploaded scene_cache.py failed checksum validation.\n' >&2
    exit 6
fi
if [ "$(hash_file "$stage/coordinator.py")" != "$patched_coordinator" ]; then
    printf 'Uploaded coordinator.py failed checksum validation.\n' >&2
    exit 6
fi

backup_scene="$base/scene_cache.py.$backup_suffix"
backup_coordinator="$base/coordinator.py.$backup_suffix"
if [ -e "$backup_scene" ] || [ -e "$backup_coordinator" ]; then
    printf 'Backup name collision; refusing commit.\n' >&2
    exit 7
fi

cp -p "$base/scene_cache.py" "$backup_scene"
cp -p "$base/coordinator.py" "$backup_coordinator"
chmod 0644 "$stage/scene_cache.py" "$stage/coordinator.py"

scene_replaced=0
coordinator_replaced=0
committed=0
rollback() {
    exit_code=$?
    trap - EXIT HUP INT TERM
    if [ "$committed" -eq 0 ]; then
        if [ "$scene_replaced" -eq 1 ]; then
            cp -p "$backup_scene" "$base/scene_cache.py"
        fi
        if [ "$coordinator_replaced" -eq 1 ]; then
            cp -p "$backup_coordinator" "$base/coordinator.py"
        fi
    fi
    rm -rf -- "$stage"
    exit "$exit_code"
}
trap rollback EXIT HUP INT TERM

mv -f "$stage/scene_cache.py" "$base/scene_cache.py"
scene_replaced=1
mv -f "$stage/coordinator.py" "$base/coordinator.py"
coordinator_replaced=1

if [ "$(hash_file "$base/scene_cache.py")" != "$patched_scene" ] || \
   [ "$(hash_file "$base/coordinator.py")" != "$patched_coordinator" ]; then
    printf 'Post-commit checksum validation failed; rolling back.\n' >&2
    exit 8
fi

committed=1
trap - EXIT HUP INT TERM
rm -rf -- "$stage"
printf 'Applied Govee scene-cache hotfix. Backups:\n'
printf '  %s\n  %s\n' "$backup_scene" "$backup_coordinator"
REMOTE_APPLY

REMOTE_STAGE=""
printf 'Files are installed. Home Assistant was not restarted or reloaded.\n'
