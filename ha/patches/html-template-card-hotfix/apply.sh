#!/usr/bin/env bash

set -euo pipefail

readonly REMOTE_DIR="/config/www/community/Home-Assistant-Lovelace-HTML-Jinja2-Template-card"
readonly EXPECTED_JS_SHA256="7132e9d84b9f281b80f067c4506ac7743e0ecc84134fbf7830542cfa6d13e9d3"
readonly EXPECTED_GZIP_SHA256="1e6af08cd5fd47e84bb35e8e44fb0ce19325452a515c9c52905f60f20e76f321"
readonly PREVIOUS_JS_SHA256="294483f8d04a1a242e815f3b352459191d06abd950ae82ec6cc41bd7f7cbc4ae"
readonly PREVIOUS_GZIP_SHA256="ebb47e8842a447affccc591065fa2e0e5e57b6d7811f4af5750532f466e7575f"

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

for required_command in ssh mktemp gzip node; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        printf 'Required local command not found: %s\n' "$required_command" >&2
        exit 2
    fi
done

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly OVERLAY="$SCRIPT_DIR/html-template-card.js"

if [[ ! -f "$OVERLAY" ]]; then
    printf 'Hotfix overlay not found: %s\n' "$OVERLAY" >&2
    exit 2
fi

STAGE_DIR="$(mktemp -d /tmp/html-template-card-hotfix.XXXXXX)"
readonly STAGE_DIR
REMOTE_STAGE=""

cleanup() {
    local exit_code=$?
    trap - EXIT
    if [[ -n "$REMOTE_STAGE" ]]; then
        ssh "$SSH_TARGET" sudo sh -s -- "$REMOTE_STAGE" <<'REMOTE_CLEANUP' >/dev/null 2>&1 || true
stage=$1
case "$stage" in
    /tmp/html-template-card-hotfix.*) rm -rf -- "$stage" ;;
esac
REMOTE_CLEANUP
    fi
    rm -rf -- "$STAGE_DIR"
    exit "$exit_code"
}
trap cleanup EXIT

cp "$OVERLAY" "$STAGE_DIR/html-template-card.js"
node --check "$STAGE_DIR/html-template-card.js"
gzip -n -9 -c "$STAGE_DIR/html-template-card.js" \
    > "$STAGE_DIR/html-template-card.js.gz"
gzip -t "$STAGE_DIR/html-template-card.js.gz"
gzip -dc "$STAGE_DIR/html-template-card.js.gz" \
    > "$STAGE_DIR/html-template-card.js.expanded"
if ! cmp -s \
    "$STAGE_DIR/html-template-card.js" \
    "$STAGE_DIR/html-template-card.js.expanded"; then
    printf 'Generated gzip does not expand to the hotfix JavaScript.\n' >&2
    exit 4
fi

# These guards catch accidental replacement with a generation-only fix.  Strict
# maximum-one behavior requires awaiting both asynchronous lifecycle phases.
if [[ "$(grep -c 'await desired.connection.subscribeMessage' "$STAGE_DIR/html-template-card.js")" -ne 1 ]]; then
    printf 'Hotfix must await exactly one subscribeMessage call site.\n' >&2
    exit 4
fi
if [[ "$(grep -c 'await active.unsubscribe()' "$STAGE_DIR/html-template-card.js")" -ne 1 ]]; then
    printf 'Hotfix must await exactly one unsubscribe call site.\n' >&2
    exit 4
fi
if [[ "$(grep -c 'disconnectedCallback()' "$STAGE_DIR/html-template-card.js")" -ne 1 ]]; then
    printf 'Hotfix disconnected cleanup hook is missing or duplicated.\n' >&2
    exit 4
fi

patched_js_sha256="$(sha256_file "$STAGE_DIR/html-template-card.js")"
patched_gzip_sha256="$(sha256_file "$STAGE_DIR/html-template-card.js.gz")"

# Read-only compatibility fetch.  Both source artifacts are pinned because the
# HTTP server may serve the precompressed file instead of the plain JavaScript.
ssh "$SSH_TARGET" "cat '$REMOTE_DIR/html-template-card.js'" \
    > "$STAGE_DIR/html-template-card.js.remote"
ssh "$SSH_TARGET" "cat '$REMOTE_DIR/html-template-card.js.gz'" \
    > "$STAGE_DIR/html-template-card.js.gz.remote"

actual_js_sha256="$(sha256_file "$STAGE_DIR/html-template-card.js.remote")"
actual_gzip_sha256="$(sha256_file "$STAGE_DIR/html-template-card.js.gz.remote")"

remote_gzip_expands_to="invalid"
if gzip -t "$STAGE_DIR/html-template-card.js.gz.remote" 2>/dev/null; then
    gzip -dc "$STAGE_DIR/html-template-card.js.gz.remote" \
        > "$STAGE_DIR/html-template-card.js.remote-expanded"
    remote_gzip_expands_to="$(sha256_file "$STAGE_DIR/html-template-card.js.remote-expanded")"
fi

# Accept an already-installed hotfix even when a different gzip implementation
# produced different container bytes; the served expanded JavaScript must still
# be byte-for-byte identical to this overlay.
if [[ "$actual_js_sha256" == "$patched_js_sha256" \
    && "$remote_gzip_expands_to" == "$patched_js_sha256" ]]; then
    printf 'Hotfix is already installed; plain and gzip resources expand to %s.\n' \
        "$patched_js_sha256"
    exit 0
fi

source_label=""
if [[ "$actual_js_sha256" == "$EXPECTED_JS_SHA256" \
    && "$actual_gzip_sha256" == "$EXPECTED_GZIP_SHA256" ]]; then
    source_label="upstream v1.0.2"
elif [[ "$actual_js_sha256" == "$PREVIOUS_JS_SHA256" \
    && "$actual_gzip_sha256" == "$PREVIOUS_GZIP_SHA256" ]]; then
    source_label="previous lifecycle hotfix"
else
    printf 'Refusing: remote resource pair is unreviewed (%s, %s).\n' \
        "$actual_js_sha256" "$actual_gzip_sha256" >&2
    exit 3
fi
if [[ "$remote_gzip_expands_to" != "$actual_js_sha256" ]]; then
    printf 'Refusing: remote gzip does not expand to the reviewed JavaScript.\n' >&2
    exit 3
fi

if [[ "$MODE" == "--check" ]]; then
    printf 'CHECK ONLY: compatible %s resources found.\n' "$source_label"
    printf '  staged JavaScript %s\n' "$patched_js_sha256"
    printf '  staged gzip      %s\n' "$patched_gzip_sha256"
    printf 'No remote files were changed.\n'
    exit 0
fi

backup_suffix="pre-subscription-hotfix-$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_STAGE="$(ssh "$SSH_TARGET" "mktemp -d '/tmp/html-template-card-hotfix.XXXXXX'")"
case "$REMOTE_STAGE" in
    /tmp/html-template-card-hotfix.*) ;;
    *)
        printf 'Refusing unexpected remote staging path: %s\n' "$REMOTE_STAGE" >&2
        exit 5
        ;;
esac

ssh "$SSH_TARGET" "umask 077; cat > '$REMOTE_STAGE/html-template-card.js'" \
    < "$STAGE_DIR/html-template-card.js"
ssh "$SSH_TARGET" "umask 077; cat > '$REMOTE_STAGE/html-template-card.js.gz'" \
    < "$STAGE_DIR/html-template-card.js.gz"

# The unprivileged SSH user owns /tmp staging.  The sudo commit first copies each
# artifact into a same-directory root-owned temporary file, so the final renames
# are atomic even when /tmp and /config are different filesystems.
ssh "$SSH_TARGET" sudo sh -s -- \
    "$REMOTE_STAGE" \
    "$backup_suffix" \
    "$actual_js_sha256" \
    "$actual_gzip_sha256" \
    "$patched_js_sha256" \
    "$patched_gzip_sha256" <<'REMOTE_APPLY'
set -eu

stage=$1
backup_suffix=$2
expected_js=$3
expected_gzip=$4
patched_js=$5
patched_gzip=$6
base=/config/www/community/Home-Assistant-Lovelace-HTML-Jinja2-Template-card
target_js=$base/html-template-card.js
target_gzip=$base/html-template-card.js.gz

case "$stage" in
    /tmp/html-template-card-hotfix.*) ;;
    *)
        printf 'Unexpected staging path: %s\n' "$stage" >&2
        exit 5
        ;;
esac

hash_file() {
    sha256sum "$1" | awk '{print $1}'
}

if [ "$(hash_file "$target_js")" != "$expected_js" ]; then
    printf 'html-template-card.js changed after validation; refusing commit.\n' >&2
    exit 6
fi
if [ "$(hash_file "$target_gzip")" != "$expected_gzip" ]; then
    printf 'html-template-card.js.gz changed after validation; refusing commit.\n' >&2
    exit 6
fi
if [ "$(hash_file "$stage/html-template-card.js")" != "$patched_js" ]; then
    printf 'Uploaded JavaScript failed checksum validation.\n' >&2
    exit 6
fi
if [ "$(hash_file "$stage/html-template-card.js.gz")" != "$patched_gzip" ]; then
    printf 'Uploaded gzip failed checksum validation.\n' >&2
    exit 6
fi
if ! gzip -t "$stage/html-template-card.js.gz"; then
    printf 'Uploaded gzip failed integrity validation.\n' >&2
    exit 6
fi
if [ "$(gzip -dc "$stage/html-template-card.js.gz" | sha256sum | awk '{print $1}')" != "$patched_js" ]; then
    printf 'Uploaded gzip does not contain the uploaded JavaScript.\n' >&2
    exit 6
fi

backup_js=$target_js.$backup_suffix
backup_gzip=$target_gzip.$backup_suffix
if [ -e "$backup_js" ] || [ -e "$backup_gzip" ]; then
    printf 'Backup name collision; refusing commit.\n' >&2
    exit 7
fi

js_uid=$(stat -c '%u' "$target_js")
js_gid=$(stat -c '%g' "$target_js")
js_mode=$(stat -c '%a' "$target_js")
gzip_uid=$(stat -c '%u' "$target_gzip")
gzip_gid=$(stat -c '%g' "$target_gzip")
gzip_mode=$(stat -c '%a' "$target_gzip")

commit_js=
commit_gzip=
js_replaced=0
gzip_replaced=0
backup_js_created=0
backup_gzip_created=0
committed=0

restore_atomic() {
    restore_source=$1
    restore_target=$2
    restore_temp=$(mktemp "$base/.html-template-card.rollback.XXXXXX") || return 1
    if ! cp -p "$restore_source" "$restore_temp"; then
        rm -f -- "$restore_temp"
        return 1
    fi
    if ! mv -f "$restore_temp" "$restore_target"; then
        rm -f -- "$restore_temp"
        return 1
    fi
}

rollback() {
    exit_code=$?
    trap - EXIT HUP INT TERM
    set +e
    rollback_failed=0
    if [ "$committed" -eq 0 ]; then
        if [ "$js_replaced" -eq 1 ]; then
            restore_atomic "$backup_js" "$target_js" || rollback_failed=1
        fi
        if [ "$gzip_replaced" -eq 1 ]; then
            restore_atomic "$backup_gzip" "$target_gzip" || rollback_failed=1
        fi
    fi
    if [ -n "$commit_js" ]; then
        rm -f -- "$commit_js"
    fi
    if [ -n "$commit_gzip" ]; then
        rm -f -- "$commit_gzip"
    fi
    if [ "$js_replaced" -eq 0 ] && [ "$gzip_replaced" -eq 0 ]; then
        if [ "$backup_js_created" -eq 1 ]; then
            rm -f -- "$backup_js"
        fi
        if [ "$backup_gzip_created" -eq 1 ]; then
            rm -f -- "$backup_gzip"
        fi
    fi
    rm -rf -- "$stage"
    if [ "$rollback_failed" -ne 0 ]; then
        printf 'CRITICAL: automatic rollback failed; backups are %s and %s\n' \
            "$backup_js" "$backup_gzip" >&2
        exit 90
    fi
    exit "$exit_code"
}
trap rollback EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

commit_js=$(mktemp "$base/.html-template-card.js.hotfix.XXXXXX")
commit_gzip=$(mktemp "$base/.html-template-card.js.gz.hotfix.XXXXXX")
cp "$stage/html-template-card.js" "$commit_js"
cp "$stage/html-template-card.js.gz" "$commit_gzip"
chown "$js_uid:$js_gid" "$commit_js"
chown "$gzip_uid:$gzip_gid" "$commit_gzip"
chmod "$js_mode" "$commit_js"
chmod "$gzip_mode" "$commit_gzip"

if [ "$(hash_file "$commit_js")" != "$patched_js" ] || \
   [ "$(hash_file "$commit_gzip")" != "$patched_gzip" ]; then
    printf 'Same-directory commit staging failed checksum validation.\n' >&2
    exit 7
fi

backup_js_created=1
cp -p "$target_js" "$backup_js"
backup_gzip_created=1
cp -p "$target_gzip" "$backup_gzip"

# Both source and destination are in $base, making each rename atomic.
mv -f "$commit_js" "$target_js"
js_replaced=1
mv -f "$commit_gzip" "$target_gzip"
gzip_replaced=1

if [ "$(hash_file "$target_js")" != "$patched_js" ] || \
   [ "$(hash_file "$target_gzip")" != "$patched_gzip" ]; then
    printf 'Post-commit checksum validation failed; rolling back both files.\n' >&2
    exit 8
fi
if [ "$(gzip -dc "$target_gzip" | sha256sum | awk '{print $1}')" != "$patched_js" ]; then
    printf 'Installed gzip content validation failed; rolling back both files.\n' >&2
    exit 8
fi

committed=1
trap - EXIT HUP INT TERM
rm -rf -- "$stage"
printf 'Applied html-template-card lifecycle hotfix. Backups:\n'
printf '  %s\n  %s\n' "$backup_js" "$backup_gzip"
REMOTE_APPLY

REMOTE_STAGE=""
printf 'Plain and gzip resources are installed. Home Assistant was not restarted or reloaded.\n'
