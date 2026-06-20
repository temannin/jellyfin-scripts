#!/usr/bin/env python3
"""
check_jellyfin.py - Flag video files that may not direct play in Jellyfin
Usage: python check_jellyfin.py /path/to/media/**/*.mkv
       python check_jellyfin.py /media/movies/
"""

import json
import subprocess
import sys
from pathlib import Path

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".wmv"}
SAFE_CODECS = {"h264", "hevc", "av1", "vp9"}


def probe(file: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            str(file),
        ],
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def get_stream(data: dict, codec_type: str) -> dict:
    for stream in data.get("streams", []):
        if stream.get("codec_type") == codec_type:
            return stream
    return {}


def check_file(file: Path) -> list[str]:
    issues = []

    try:
        data = probe(file)
    except (subprocess.SubprocessError, json.JSONDecodeError) as e:
        return [f"Could not probe file: {e}"]

    video = get_stream(data, "video")
    if not video:
        return ["No video stream found"]

    codec = video.get("codec_name", "unknown")
    level = int(video.get("level", 0))
    refs = int(video.get("refs", 0))
    depth = int(video.get("bits_per_raw_sample") or video.get("bits_per_coded_sample") or 8)
    sar = video.get("sample_aspect_ratio", "1:1")
    dar = video.get("display_aspect_ratio", "")
    width = video.get("width", 0)
    height = video.get("height", 0)
    field_order = video.get("field_order", "progressive")
    pix_fmt = video.get("pix_fmt", "")

    # Anamorphic (non-square pixels)
    if sar and sar != "1:1" and sar != "0:1":
        issues.append(f"Anamorphic — SAR: {sar}, stored: {width}x{height}, display AR: {dar}")

    # Codec
    if codec not in SAFE_CODECS:
        issues.append(f"Codec '{codec}' may need transcoding")

    # H264 level (42 = 4.2, stored as int)
    if codec == "h264" and level > 40:
        issues.append(f"H264 level {level / 10:.1f} — may not direct play on all clients")

    # Ref frames
    if refs > 4:
        issues.append(f"High ref frames: {refs} (problematic on some clients)")

    # Bit depth
    if depth > 8:
        issues.append(f"{depth}-bit video — HDR/10-bit may need transcoding")

    # Interlaced
    if field_order not in ("progressive", "unknown", ""):
        issues.append(f"Interlaced ({field_order})")

    # Pixel format (4:2:0 is safe; 4:4:4 or 4:2:2 often can't direct play)
    if pix_fmt and "420" not in pix_fmt:
        issues.append(f"Pixel format '{pix_fmt}' — 4:2:0 is safest for direct play")

    return issues


def scan(paths: list[Path]) -> None:
    files = []
    for path in paths:
        if path.is_dir():
            for ext in VIDEO_EXTENSIONS:
                files.extend(path.rglob(f"*{ext}"))
        elif path.suffix.lower() in VIDEO_EXTENSIONS:
            files.append(path)
        else:
            print(f"⚠️  Skipping (not a video): {path}")

    if not files:
        print("No video files found.")
        return

    ok = 0
    flagged = 0

    for file in sorted(files):
        issues = check_file(file)
        if issues:
            flagged += 1
            print(f"\n⚠️  {file}")
            for issue in issues:
                print(f"   • {issue}")
        else:
            ok += 1
            print(f"✅  {file}")

    print(f"\n{'─' * 60}")
    print(f"  {ok} OK    {flagged} flagged    {ok + flagged} total")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_jellyfin.py <file_or_directory> [...]")
        sys.exit(1)

    scan([Path(p) for p in sys.argv[1:]])