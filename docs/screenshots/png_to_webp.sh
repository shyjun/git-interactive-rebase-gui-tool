#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in "$SCRIPT_DIR"/*.png; do
    [ -e "$f" ] || continue
    cwebp "$f" -q 85 -o "${f%.png}.webp"
    rm -fv "$f"
done
