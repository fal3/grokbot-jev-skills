#!/usr/bin/env bash
# grokbot-jev-skills installer.
#
# Installs the upstream Jev CLI (github.com/kerpopule/hermes-jev-skills) pinned to a tested
# commit, writes a small `jev` launcher, and optionally copies this repo's skills into a
# Grok Bot skill folder. It never asks for, reads, prints or stores an API key.
#
#   bash install.sh --check        show what would happen, change nothing
#   bash install.sh                install (idempotent; re-run to repair or update)
#   bash install.sh --uninstall    remove only what this installer created
#
# Options (each also settable through the environment variable shown):
#   --dir DIR          upstream checkout          [JEV_UPSTREAM_DIR, ~/.local/share/hermes-jev-skills]
#   --ref REF          upstream commit or tag     [JEV_UPSTREAM_REF, the pinned commit below]
#   --upstream URL     upstream git URL           [JEV_UPSTREAM_URL, https://github.com/kerpopule/hermes-jev-skills]
#   --bin-dir DIR      where the launcher goes    [JEV_BIN_DIR, ~/.local/bin]
#   --skills-dir DIR   Grok Bot skill folder      [GROKBOT_SKILLS_DIR, /home/box/agent-data/workflows if it exists]
#   --no-skills        do not install skills
#   --force            overwrite skill files that were edited since they were installed
set -euo pipefail

# Upstream v0.22.1 as tested: the main-branch commit right after the v0.22.1 tag (4e9b367),
# which adds one redaction fix. Both report version 0.22.1.
PINNED_REF="a6f6344bae3411b2afaabd640dc28cda736e8894"
DEFAULT_URL="https://github.com/kerpopule/hermes-jev-skills"
# Where Grok Bot reads user skills. GROKBOT_DEFAULT_SKILLS_PROBE overrides it (used by the tests).
GROKBOT_DEFAULT_SKILLS="${GROKBOT_DEFAULT_SKILLS_PROBE:-/home/box/agent-data/workflows}"
MARKER="# grokbot-jev-skills launcher"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="install"
UP_DIR="${JEV_UPSTREAM_DIR:-$HOME/.local/share/hermes-jev-skills}"
UP_REF="${JEV_UPSTREAM_REF:-$PINNED_REF}"
UP_URL="${JEV_UPSTREAM_URL:-$DEFAULT_URL}"
BIN_DIR="${JEV_BIN_DIR:-$HOME/.local/bin}"
SKILLS_DIR="${GROKBOT_SKILLS_DIR:-}"
SKILLS_DIR_EXPLICIT=0
[ -n "$SKILLS_DIR" ] && SKILLS_DIR_EXPLICIT=1
NO_SKILLS=0
FORCE=0
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}"
MANIFEST="$STATE_DIR/grokbot-jev-skills/installed-skills.tsv"

usage() { sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "error: $*" >&2; exit 1; }
say() { echo "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --uninstall) MODE="uninstall" ;;
    --dir) UP_DIR="${2:?--dir needs a path}"; shift ;;
    --ref) UP_REF="${2:?--ref needs a commit or tag}"; shift ;;
    --upstream) UP_URL="${2:?--upstream needs a URL}"; shift ;;
    --bin-dir) BIN_DIR="${2:?--bin-dir needs a path}"; shift ;;
    --skills-dir) SKILLS_DIR="${2:?--skills-dir needs a path}"; SKILLS_DIR_EXPLICIT=1; shift ;;
    --no-skills) NO_SKILLS=1 ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
  shift
done

if [ "$NO_SKILLS" -eq 0 ] && [ "$SKILLS_DIR_EXPLICIT" -eq 0 ] && [ -d "$GROKBOT_DEFAULT_SKILLS" ]; then
  SKILLS_DIR="$GROKBOT_DEFAULT_SKILLS"
fi
[ "$NO_SKILLS" -eq 1 ] && SKILLS_DIR=""

# shellcheck disable=SC1003  # the last pattern is a literal backslash
case "$UP_DIR" in *'"'*|*'$'*|*'`'*|*'\'*) die "--dir must not contain quotes, \$, backticks or backslashes" ;; esac

LAUNCHER="$BIN_DIR/jev"
SLUGS=()
for f in "$HERE"/skills/*/SKILL.md; do
  [ -f "$f" ] || continue
  SLUGS+=("$(basename "$(dirname "$f")")")
done

sha() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}
ours_launcher() { [ -f "$LAUNCHER" ] && grep -qF "$MARKER" "$LAUNCHER"; }
ours_checkout() { [ -f "$UP_DIR/.git/grokbot-jev-skills-managed" ]; }
recorded_sha() { [ -f "$MANIFEST" ] && awk -F'\t' -v p="$1" '$1 == p {print $2}' "$MANIFEST" | tail -n 1; }
launcher_text() {
  cat <<LAUNCHER
#!/bin/sh
$MARKER (managed by install.sh; remove with install.sh --uninstall)
# Runs the pinned upstream Jev CLI. Jev's local decision ledger and spend counters go to
# ~/.local/state/jev instead of ~/.hermes. The API key is read from TYPESAFE_API_KEY.
: "\${HERMES_HOME:=\$HOME/.local/state/jev}"
export HERMES_HOME
exec "$UP_DIR/bin/jev" "\$@"
LAUNCHER
}

preflight() {
  command -v git >/dev/null 2>&1 || die "git is required"
  command -v python3 >/dev/null 2>&1 || die "python3 is required"
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || die "python3 3.9 or newer is required"
}

# ── check ────────────────────────────────────────────────────────────────────
if [ "$MODE" = "check" ]; then
  say "grokbot-jev-skills install plan (nothing will be changed)"
  for tool in git python3; do
    if command -v "$tool" >/dev/null 2>&1; then say "  ok      $tool found"; else say "  MISSING $tool"; fi
  done
  if command -v python3 >/dev/null 2>&1; then
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
      say "  ok      python3 >= 3.9"
    else
      say "  MISSING python3 >= 3.9"
    fi
  fi
  if [ -d "$UP_DIR/.git" ]; then
    say "  upstream  $UP_DIR exists; would check out $UP_REF"
  elif [ -e "$UP_DIR" ]; then
    say "  CONFLICT  $UP_DIR exists and is not a git checkout; install would stop"
  else
    say "  upstream  would clone $UP_URL into $UP_DIR at $UP_REF"
  fi
  if [ -e "$LAUNCHER" ] && ! ours_launcher; then
    say "  CONFLICT  $LAUNCHER exists and was not written by this installer; install would stop"
  else
    say "  launcher  would write $LAUNCHER"
  fi
  case ":$PATH:" in *":$BIN_DIR:"*) say "  ok      $BIN_DIR is on PATH" ;; *) say "  note    $BIN_DIR is not on PATH; call $LAUNCHER directly" ;; esac
  if [ -n "$SKILLS_DIR" ]; then
    say "  skills    would copy ${#SLUGS[@]} skills into $SKILLS_DIR/<slug>/SKILL.md"
  else
    say "  skills    none (no --skills-dir, and $GROKBOT_DEFAULT_SKILLS does not exist)"
  fi
  say "  key       never touched; set TYPESAFE_API_KEY in the environment yourself"
  exit 0
fi

# ── uninstall ────────────────────────────────────────────────────────────────
if [ "$MODE" = "uninstall" ]; then
  if ours_launcher; then rm -f "$LAUNCHER"; say "removed   $LAUNCHER"
  elif [ -e "$LAUNCHER" ]; then say "kept      $LAUNCHER (not written by this installer)"; fi
  if ours_checkout; then rm -rf "$UP_DIR"; say "removed   $UP_DIR"
  elif [ -e "$UP_DIR" ]; then say "kept      $UP_DIR (not created by this installer)"; fi
  if [ -f "$MANIFEST" ]; then
    while IFS=$'\t' read -r path digest; do
      [ -n "$path" ] || continue
      if [ -f "$path" ] && [ "$(sha "$path")" = "$digest" ]; then
        rm -f "$path"; rmdir "$(dirname "$path")" 2>/dev/null || true; say "removed   $path"
      elif [ -f "$path" ]; then
        say "kept      $path (edited since install)"
      fi
    done < "$MANIFEST"
    rm -f "$MANIFEST"; rmdir "$(dirname "$MANIFEST")" 2>/dev/null || true
  fi
  say "left      ${STATE_DIR}/jev (jev's local decision log; delete it yourself if you want)"
  exit 0
fi

# ── install ──────────────────────────────────────────────────────────────────
preflight
if [ -e "$LAUNCHER" ] && ! ours_launcher; then
  die "$LAUNCHER exists and was not written by this installer; move it aside or pass --bin-dir"
fi

if [ -d "$UP_DIR/.git" ]; then
  if ! ours_checkout; then
    origin="$(git -C "$UP_DIR" remote get-url origin 2>/dev/null || true)"
    [ "${origin%.git}" = "${UP_URL%.git}" ] || die "$UP_DIR is a git checkout of '$origin', not $UP_URL; pass --dir"
  fi
  if ! git -C "$UP_DIR" rev-parse --quiet --verify "$UP_REF^{commit}" >/dev/null; then
    git -C "$UP_DIR" fetch --quiet --tags origin
  fi
  say "upstream  $UP_DIR (existing checkout)"
elif [ -e "$UP_DIR" ]; then
  die "$UP_DIR exists and is not a git checkout; pass --dir"
else
  mkdir -p "$(dirname "$UP_DIR")"
  git clone --quiet --no-checkout "$UP_URL" "$UP_DIR"
  say "upstream  cloned $UP_URL into $UP_DIR"
fi
commit="$(git -C "$UP_DIR" rev-parse --verify "$UP_REF^{commit}")" || die "upstream has no commit or tag '$UP_REF'"
git -C "$UP_DIR" -c advice.detachedHead=false checkout --quiet --detach "$commit"
: > "$UP_DIR/.git/grokbot-jev-skills-managed"
say "upstream  checked out $commit"

mkdir -p "$BIN_DIR"
tmp="$LAUNCHER.tmp.$$"
launcher_text > "$tmp"
chmod 755 "$tmp"
mv -f "$tmp" "$LAUNCHER"
say "launcher  $LAUNCHER"
version="$("$LAUNCHER" --version 2>/dev/null)" || die "$LAUNCHER --version failed"
say "jev       $version"

if [ -n "$SKILLS_DIR" ]; then
  mkdir -p "$SKILLS_DIR" "$(dirname "$MANIFEST")"
  touch "$MANIFEST"
  for slug in "${SLUGS[@]}"; do
    src="$HERE/skills/$slug/SKILL.md"
    dst="$SKILLS_DIR/$slug/SKILL.md"
    if [ -f "$dst" ]; then
      current="$(sha "$dst")"
      if [ "$current" = "$(sha "$src")" ]; then say "skill     $slug (unchanged)"; continue; fi
      if [ "$current" != "$(recorded_sha "$dst")" ] && [ "$FORCE" -eq 0 ]; then
        say "skill     $slug SKIPPED: $dst was not written by this installer or was edited (use --force)"
        continue
      fi
    fi
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    awk -F'\t' -v p="$dst" '$1 != p' "$MANIFEST" > "$MANIFEST.tmp" && mv -f "$MANIFEST.tmp" "$MANIFEST"
    printf '%s\t%s\n' "$dst" "$(sha "$dst")" >> "$MANIFEST"
    say "skill     $slug -> $dst"
  done
else
  say "skills    not installed (no --skills-dir, and $GROKBOT_DEFAULT_SKILLS does not exist)"
fi

case ":$PATH:" in *":$BIN_DIR:"*) ;; *) say "note      $BIN_DIR is not on PATH; use $LAUNCHER" ;; esac
say "next      set TYPESAFE_API_KEY in the environment (never in chat), then run: jev doctor"
