#!/usr/bin/env bash
set -euo pipefail

# Setup superpowers for OpenAI Codex via native skill discovery
# https://github.com/obra/superpowers

REPO_URL="https://github.com/obra/superpowers.git"
CLONE_DIR="$HOME/.codex/superpowers"
SKILLS_DIR="$HOME/.agents/skills"

echo "=== Codex Superpowers Setup ==="

# Clone or update
if [ -d "$CLONE_DIR" ]; then
  echo "Updating existing superpowers..."
  git -C "$CLONE_DIR" pull --ff-only
else
  echo "Cloning superpowers..."
  mkdir -p "$(dirname "$CLONE_DIR")"
  git clone "$REPO_URL" "$CLONE_DIR"
fi

# Create skills symlink
mkdir -p "$SKILLS_DIR"
if [ -L "$SKILLS_DIR/superpowers" ] || [ -d "$SKILLS_DIR/superpowers" ]; then
  echo "Skills symlink already exists, recreating..."
  rm -f "$SKILLS_DIR/superpowers"
fi
ln -s "$CLONE_DIR/skills" "$SKILLS_DIR/superpowers"

echo ""
echo "Done! Restart Codex to discover skills."
echo "Verify: ls -la $SKILLS_DIR/superpowers"
