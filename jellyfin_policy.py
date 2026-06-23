#!/usr/bin/env python3
"""
jellyfin_policy.py - Manage Jellyfin user playback policies

Reads config from environment variables:
  $env:JELLYFIN_URL     e.g. http://localhost:8096
  $env:JELLYFIN_API_KEY your Jellyfin API key

Usage:
  python jellyfin_policy.py --enable-remux
  python jellyfin_policy.py --disable-remux
  python jellyfin_policy.py --enable-transcoding
  python jellyfin_policy.py --disable-transcoding
  python jellyfin_policy.py --enable-downloads
  python jellyfin_policy.py --disable-downloads
  python jellyfin_policy.py --enable-all
  python jellyfin_policy.py --disable-all
  python jellyfin_policy.py --status
  python jellyfin_policy.py --user tyler --enable-remux
"""

import json
import os
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError


POLICY_FLAGS = {
    "remux":               "EnablePlaybackRemuxing",
    "video-transcoding":   "EnableVideoPlaybackTranscoding",
    "audio-transcoding":   "EnableAudioPlaybackTranscoding",
    "downloads":           "EnableContentDownloading",
}


def jellyfin_request(method: str, url: str, api_key: str, body: dict = None) -> dict:
    headers = {
        "Authorization": f'MediaBrowser Token="{api_key}"',
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req) as resp:
        content = resp.read()
        return json.loads(content) if content else {}


def get_users(server: str, api_key: str, username: str = None) -> list:
    try:
        users = jellyfin_request("GET", f"{server}/Users", api_key)
    except URLError as e:
        print(f"❌ Could not connect to Jellyfin: {e}")
        sys.exit(1)

    if username:
        users = [u for u in users if u.get("Name", "").lower() == username.lower()]
        if not users:
            print(f"❌ User '{username}' not found")
            sys.exit(1)

    return users


def apply_policy(server: str, api_key: str, changes: dict, username: str = None) -> None:
    users = get_users(server, api_key, username)

    for user in users:
        name = user.get("Name", "unknown")
        uid = user.get("Id")
        policy = user.get("Policy", {})

        for key, value in changes.items():
            policy[key] = value

        try:
            jellyfin_request("POST", f"{server}/Users/{uid}/Policy", api_key, policy)
            changes_str = ", ".join(
                f"{k.replace('Enable', '').replace('Playback', '')}={'on' if v else 'off'}"
                for k, v in changes.items()
            )
            print(f"✅  {name} — {changes_str}")
        except URLError as e:
            print(f"❌  {name} — failed: {e}")


def print_status(server: str, api_key: str, username: str = None) -> None:
    users = get_users(server, api_key, username)

    col = 20
    header = f"{'User':<{col}} {'Remux':<8} {'Video TX':<10} {'Audio TX':<10} {'Downloads':<11}"
    print(f"\n{header}")
    print("─" * len(header))

    for user in users:
        name = user.get("Name", "unknown")
        policy = user.get("Policy", {})
        remux  = "✅" if policy.get("EnablePlaybackRemuxing") else "❌"
        vtx    = "✅" if policy.get("EnableVideoPlaybackTranscoding") else "❌"
        atx    = "✅" if policy.get("EnableAudioPlaybackTranscoding") else "❌"
        dl     = "✅" if policy.get("EnableContentDownloading") else "❌"
        print(f"{name:<{col}} {remux:<8} {vtx:<10} {atx:<10} {dl:<11}")

    print()


def usage():
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    server = os.environ.get("JELLYFIN_URL", "").rstrip("/")
    api_key = os.environ.get("JELLYFIN_API_KEY", "")

    if not server:
        print("❌ JELLYFIN_URL environment variable not set")
        sys.exit(1)
    if not api_key:
        print("❌ JELLYFIN_API_KEY environment variable not set")
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        usage()

    # Optional --user filter
    username = None
    if "--user" in args:
        idx = args.index("--user")
        try:
            username = args[idx + 1]
            args = args[:idx] + args[idx + 2:]
        except IndexError:
            print("❌ --user requires a username")
            sys.exit(1)

    command = args[0] if args else None

    COMMANDS = {
        "--enable-remux":          {POLICY_FLAGS["remux"]: True},
        "--disable-remux":         {POLICY_FLAGS["remux"]: False},
        "--enable-transcoding":    {POLICY_FLAGS["video-transcoding"]: True,  POLICY_FLAGS["audio-transcoding"]: True},
        "--disable-transcoding":   {POLICY_FLAGS["video-transcoding"]: False, POLICY_FLAGS["audio-transcoding"]: False},
        "--enable-downloads":      {POLICY_FLAGS["downloads"]: True},
        "--disable-downloads":     {POLICY_FLAGS["downloads"]: False},
        "--enable-all":            {v: True  for v in POLICY_FLAGS.values()},
        "--disable-all":           {v: False for v in POLICY_FLAGS.values()},
    }

    if command == "--status":
        print_status(server, api_key, username)
    elif command in COMMANDS:
        target = f"user '{username}'" if username else "all users"
        print(f"Applying '{command}' to {target}...")
        apply_policy(server, api_key, COMMANDS[command], username)
    else:
        usage()