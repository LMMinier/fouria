#!/usr/bin/env python3
"""Build attributed production notes from YouTube captions.

Raw captions are temporary. The persistent corpus contains locally generated,
actionable summaries with source URLs and timestamps, not transcript copies.
Only ingest videos you are authorized to access and use.
"""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "corpus" / "youtube_lessons"
OLLAMA = "http://127.0.0.1:11434/api/chat"
MODEL = "fouria:studio"
OPEN_LICENSE_MARKERS = (
    "creative commons",
    "cc by",
    "cc0",
    "public domain",
)


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True)


def video_entries(url, limit):
    cmd = ["yt-dlp", "--flat-playlist", "--dump-single-json", "--playlist-end", str(limit), url]
    data = json.loads(run(*cmd).stdout)
    if data.get("entries"):
        return [{"url": e.get("webpage_url") or f"https://www.youtube.com/watch?v={e['id']}"}
                for e in data["entries"] if e and e.get("id")]
    return [{"url": data.get("webpage_url") or url}]


def metadata(url):
    data = json.loads(run("yt-dlp", "--skip-download", "--dump-single-json", url).stdout)
    return {
        "id": data.get("id"), "title": data.get("title") or "Untitled",
        "channel": data.get("channel") or data.get("uploader") or "Unknown",
        "url": data.get("webpage_url") or url,
        "license": data.get("license"), "duration": data.get("duration"),
    }


def require_open_license(meta):
    license_name = (meta.get("license") or "").strip().lower()
    if not any(marker in license_name for marker in OPEN_LICENSE_MARKERS):
        raise RuntimeError(
            "rejected: video does not declare a supported open license "
            f"(reported license: {meta.get('license') or 'unspecified'})"
        )


def captions(url, work):
    template = str(work / "%(id)s.%(ext)s")
    run("yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs",
        "--sub-langs", "en.*,en", "--sub-format", "vtt", "-o", template, url)
    files = sorted(work.glob("*.vtt"))
    if not files:
        raise RuntimeError("no English captions available")
    text = files[0].read_text(encoding="utf-8", errors="ignore")
    lines, seen = [], set()
    timestamp = "00:00"
    for raw in text.splitlines():
        line = raw.strip()
        if "-->" in line:
            timestamp = line.split("-->")[0].strip().split(".")[0]
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:")) or line in seen:
            continue
        seen.add(line)
        lines.append(f"[{timestamp}] {line}")
    return "\n".join(lines)


def ollama_notes(meta, transcript):
    prompt = f"""Create original, concise production study notes from the caption text below.
Do not reproduce the transcript. Extract techniques, decision rules, FL Studio actions,
genre conventions, common mistakes, and exercises. Preserve useful timestamps.
Ignore sponsorships, self-promotion, and unsupported claims.

SOURCE
Title: {meta['title']}
Channel: {meta['channel']}
URL: {meta['url']}

CAPTIONS
{transcript[:50000]}

Return Markdown with: Summary, Techniques, FL Studio Workflow, Genre/Style Notes,
Mixing/Mastering Notes, Exercises, and Timestamp Index. Omit empty sections."""
    body = json.dumps({"model": MODEL, "stream": False, "messages": [
        {"role": "system", "content": "You are FOURIA's careful music-production knowledge editor."},
        {"role": "user", "content": prompt},
    ], "options": {"temperature": 0.25, "num_predict": 1600}}).encode()
    req = Request(OLLAMA, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=300) as response:
        return json.loads(response.read())["message"]["content"].strip()


def ingest(url, limit):
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for item in video_entries(url, limit):
        try:
            meta = metadata(item["url"])
            require_open_license(meta)
            with tempfile.TemporaryDirectory(prefix="fouria-youtube-") as tmp:
                transcript = captions(meta["url"], Path(tmp))
                notes = ollama_notes(meta, transcript)
            slug = re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-")[:70]
            target = OUT / f"{meta['id']}-{slug}.md"
            header = (f"# {meta['title']}\n\n- Channel: {meta['channel']}\n"
                      f"- Source: {meta['url']}\n- License: {meta['license'] or 'Not specified'}\n"
                      f"- Derived notes: FOURIA local summarization\n\n")
            target.write_text(header + notes + "\n", encoding="utf-8")
            results.append({"ok": True, "source": meta["url"], "path": str(target)})
            print(f"INGESTED {meta['title']}")
        except Exception as exc:
            results.append({"ok": False, "source": item["url"], "error": str(exc)})
            print(f"SKIPPED {item['url']}: {exc}")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("urls", nargs="+", help="YouTube video, playlist, or channel URLs")
    parser.add_argument("--limit", type=int, default=20, help="maximum videos per URL")
    args = parser.parse_args()
    all_results = []
    for url in args.urls:
        all_results.extend(ingest(url, max(1, min(args.limit, 100))))
    print(json.dumps(all_results, indent=2))


if __name__ == "__main__":
    main()
