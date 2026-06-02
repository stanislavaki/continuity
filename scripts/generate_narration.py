#!/usr/bin/env python3
"""Generate ElevenLabs narration MP3s for the Toward Kontinuität landing page.

This runs LOCALLY only. Your ElevenLabs API key is read from a .env file (which
is git-ignored) or the environment and is never written into the page — the
browser only ever loads the rendered .mp3 files. That is what keeps the key off
a public static site.

Usage
-----
  python3 scripts/generate_narration.py --list-voices       # pick a voice
  python3 scripts/generate_narration.py --estimate          # char count, no API call
  python3 scripts/generate_narration.py --only intro        # render one section (test)
  python3 scripts/generate_narration.py                     # render all (skips existing)
  python3 scripts/generate_narration.py --force             # re-render everything

Credentials (.env in project root, or real environment variables):
  ELEVENLABS_API_KEY   required (except for --estimate)
  ELEVENLABS_VOICE_ID  voice to use (or pass --voice <id>)
  ELEVENLABS_MODEL_ID  optional, default eleven_multilingual_v2
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
SRC = ROOT / "scripts" / "narration.json"
OUT_DIR = ROOT / "assets" / "audio"
MANIFEST = OUT_DIR / "manifest.json"

API = "https://api.elevenlabs.io"
DEFAULT_MODEL = "eleven_multilingual_v2"
# mp3 at 44.1kHz / 128kbps — good quality, small files, broad browser support.
OUTPUT_FORMAT = "mp3_44100_128"


def load_env():
    """Populate os.environ from a .env file without overriding the real env."""
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def load_sections():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    return data["sections"]


def api_request(path, method="GET", api_key=None, json_body=None):
    headers = {"accept": "application/json"}
    if api_key:
        headers["xi-api-key"] = api_key
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(API + path, data=body, method=method, headers=headers)
    return urllib.request.urlopen(req, timeout=180)


def explain_http_error(e):
    detail = ""
    try:
        detail = e.read().decode("utf-8", "replace")
    except Exception:
        pass
    msg = f"  HTTP {e.code} {e.reason}"
    if detail:
        msg += f"\n  {detail[:500]}"
    if e.code == 401:
        msg += "\n  -> Check ELEVENLABS_API_KEY in your .env file."
    elif e.code == 422:
        msg += "\n  -> The voice id or model id may be wrong. Run --list-voices."
    return msg


def list_voices(api_key):
    try:
        resp = api_request("/v1/voices", api_key=api_key)
    except urllib.error.HTTPError as e:
        print("Failed to list voices:\n" + explain_http_error(e), file=sys.stderr)
        sys.exit(1)
    voices = json.loads(resp.read())["voices"]
    print(f"\n{len(voices)} voices on your account:\n")
    for v in voices:
        labels = v.get("labels") or {}
        tags = ", ".join(f"{k}={val}" for k, val in labels.items())
        print(f"  {v['name']:<22} {v['voice_id']}")
        if tags:
            print(f"  {'':<22} {tags}")
    print("\nSet ELEVENLABS_VOICE_ID=<id> in .env (or pass --voice <id>).\n")


def estimate(sections):
    total = sum(len(s["text"]) for s in sections)
    print("\nNarration script — character counts (count toward ElevenLabs quota):\n")
    for s in sections:
        print(f"  {s['id']:<8} {len(s['text']):>5} chars   {s['title']}")
    print(f"  {'TOTAL':<8} {total:>5} chars\n")
    print("Reference: ElevenLabs free tier ~10,000 chars/mo; Creator ~100,000/mo.")
    print("This whole narration is one small generation, re-run only when text changes.\n")
    return total


def synthesize(api_key, voice_id, model_id, text):
    path = f"/v1/text-to-speech/{voice_id}?output_format={OUTPUT_FORMAT}"
    body = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }
    headers = {"xi-api-key": api_key, "accept": "audio/mpeg", "content-type": "application/json"}
    req = urllib.request.Request(API + path, data=json.dumps(body).encode("utf-8"),
                                 method="POST", headers=headers)
    resp = urllib.request.urlopen(req, timeout=300)
    return resp.read()


def main():
    ap = argparse.ArgumentParser(description="Render ElevenLabs narration for the landing page.")
    ap.add_argument("--list-voices", action="store_true", help="list voices on your account and exit")
    ap.add_argument("--estimate", action="store_true", help="print character counts without calling the API")
    ap.add_argument("--only", metavar="IDS", help="render a subset: comma-separated ids or group prefixes (e.g. 'intro,ch1' -> intro-1, intro-2, ch1-1 … ch1-4)")
    ap.add_argument("--voice", metavar="ID", help="override ELEVENLABS_VOICE_ID")
    ap.add_argument("--model", metavar="ID", help="override ELEVENLABS_MODEL_ID")
    ap.add_argument("--force", action="store_true", help="re-render even if the mp3 already exists")
    args = ap.parse_args()

    load_env()
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    sections = load_sections()

    if args.estimate:
        estimate(sections)
        return

    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY not set. Add it to .env (see .env.example).", file=sys.stderr)
        sys.exit(1)

    if args.list_voices:
        list_voices(api_key)
        return

    voice_id = (args.voice or os.environ.get("ELEVENLABS_VOICE_ID", "")).strip()
    model_id = (args.model or os.environ.get("ELEVENLABS_MODEL_ID", "") or DEFAULT_MODEL).strip()
    if not voice_id:
        print("ERROR: no voice id. Run --list-voices, then set ELEVENLABS_VOICE_ID in .env.", file=sys.stderr)
        sys.exit(1)

    if args.only:
        wanted = [t.strip() for t in args.only.split(",") if t.strip()]
        def matches(sid):
            return any(sid == w or sid.startswith(w + "-") for w in wanted)
        sections = [s for s in sections if matches(s["id"])]
        if not sections:
            print(f"ERROR: no sections matched '{args.only}'.", file=sys.stderr)
            sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_chars = sum(len(s["text"]) for s in sections)
    print(f"Voice: {voice_id}   Model: {model_id}   Sections: {len(sections)}   Chars: {total_chars}")

    rendered = []
    for s in sections:
        out_path = OUT_DIR / f"{s['id']}.mp3"
        if out_path.exists() and not args.force:
            print(f"  skip   {s['id']}.mp3 (exists; use --force to overwrite)")
            rendered.append((s, out_path))
            continue
        print(f"  render {s['id']}.mp3 ({len(s['text'])} chars) ...", end="", flush=True)
        try:
            audio = synthesize(api_key, voice_id, model_id, s["text"])
        except urllib.error.HTTPError as e:
            print(" FAILED")
            print(explain_http_error(e), file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(" FAILED")
            print(f"  Network/SSL error: {e.reason}", file=sys.stderr)
            sys.exit(1)
        out_path.write_bytes(audio)
        print(f" {len(audio)//1024} KB")
        rendered.append((s, out_path))

    # Write/refresh the runtime manifest the page reads to play sections in order.
    manifest = {
        "voiceId": voice_id,
        "modelId": model_id,
        "outputFormat": OUTPUT_FORMAT,
        "sections": [
            {
                "id": s["id"],
                "anchor": s.get("anchor", ""),
                "title": s.get("title", ""),
                "file": f"{s['id']}.mp3",
                "bytes": p.stat().st_size,
            }
            for s, p in rendered
        ],
    }
    # Merge with any existing manifest so a --only run doesn't drop other sections.
    if MANIFEST.exists() and (args.only):
        try:
            prev = json.loads(MANIFEST.read_text(encoding="utf-8"))
            by_id = {x["id"]: x for x in prev.get("sections", [])}
            for x in manifest["sections"]:
                by_id[x["id"]] = x
            ordered_ids = [s["id"] for s in load_sections()]
            manifest["sections"] = [by_id[i] for i in ordered_ids if i in by_id]
        except Exception:
            pass
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {MANIFEST.relative_to(ROOT)} with {len(manifest['sections'])} section(s).")
    print("Reload the page — PLAY will now use the ElevenLabs audio.")


if __name__ == "__main__":
    main()
