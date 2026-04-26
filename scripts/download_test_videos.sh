#!/usr/bin/env bash
# Download 5 chat-eval test videos and clip them to 30s.
# Skips downloads that already exist. Used by docs/EVAL_REPORT.md round 2.
#
# Requires: yt-dlp + ffmpeg (brew install yt-dlp ffmpeg)
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p samples/clips

# (path-stem, ytsearch query, duration_filter)
download() {
    local stem="$1" query="$2" max_dur="$3"
    if [ -f "samples/${stem}.mp4" ]; then
        echo "✓ samples/${stem}.mp4 already exists, skip"
        return
    fi
    echo "↓ downloading ${stem}..."
    yt-dlp "ytsearch15:${query}" \
        -f "worst[height>=480][ext=mp4]" \
        --match-filter "duration < ${max_dur}" \
        --max-downloads 1 \
        -o "samples/${stem}.%(ext)s" 2>&1 | tail -3
}

download "taipei_walk"   "taipei street short clip pov"             1200
download "hk_night"      "hong kong night walk neon signs mongkok"  600
download "subway"        "tokyo subway station walking pov"         600
download "night_walk"    "night residential street walking short"   1200
download "store_indoor"  "supermarket aisle walking short clip"     1200

echo ""
echo "Clipping to 30s segments..."
for f in taipei_walk hk_night subway night_walk store_indoor; do
    if [ -f "samples/${f}.mp4" ] && [ ! -f "samples/clips/${f}_30s.mp4" ]; then
        # Try from 30s; if file is shorter, fall back to 0s
        ffmpeg -y -i "samples/${f}.mp4" -ss 30 -t 30 -c copy \
            "samples/clips/${f}_30s.mp4" 2>/dev/null
        if [ ! -s "samples/clips/${f}_30s.mp4" ] || [ $(stat -f%z "samples/clips/${f}_30s.mp4" 2>/dev/null || echo 0) -lt 10000 ]; then
            ffmpeg -y -i "samples/${f}.mp4" -ss 0 -t 30 -c copy \
                "samples/clips/${f}_30s.mp4" 2>/dev/null
        fi
        echo "  ✓ samples/clips/${f}_30s.mp4"
    fi
done

echo ""
ls -lh samples/clips/*.mp4
