#!/usr/bin/env python3
"""Build one RSS feed per configured public Xiaoyuzhou podcast."""
from __future__ import annotations

import email.utils
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

CONFIG_PATH = Path("config.json")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "atom": "http://www.w3.org/2005/Atom",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def parse_date(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        stamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(stamp, tz=timezone.utc)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        try:
            return email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None


def image_url(value):
    if isinstance(value, dict):
        return value.get("smallPicUrl") or value.get("picUrl") or value.get("url")
    return value if isinstance(value, str) else None


def fetch_source(show):
    response = requests.get(
        show["url"],
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        timeout=40,
    )
    response.raise_for_status()
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        response.text,
        flags=re.S,
    )
    if not match:
        raise RuntimeError(f'{show["name"]}: could not find __NEXT_DATA__ in the public page.')
    data = json.loads(html.unescape(match.group(1)))
    page = data.get("props", {}).get("pageProps", {})
    podcast = page.get("podcast") or {}
    raw_episodes = podcast.get("episodes") or []
    if not raw_episodes:
        raise RuntimeError(f'{show["name"]}: the public page returned no episodes.')
    return podcast, raw_episodes


def normalize_episode(raw):
    eid = raw.get("eid") or raw.get("id")
    enclosure = raw.get("enclosure") or {}
    audio = enclosure.get("url") or raw.get("audioUrl")
    if not eid or not audio:
        return None
    if urlparse(audio).scheme not in ("http", "https"):
        return None
    pub = parse_date(raw.get("pubDate") or raw.get("pub_date"))
    return {
        "eid": str(eid),
        "title": str(raw.get("title") or "Untitled episode").strip(),
        "url": "https://www.xiaoyuzhoufm.com/episode/" + str(eid),
        "audio": audio,
        "audio_type": enclosure.get("type") or "audio/mpeg",
        "audio_length": str(enclosure.get("length") or raw.get("size") or 0),
        "duration": int(raw.get("duration") or 0),
        "pub_date": pub.isoformat() if pub else None,
        "description": str(raw.get("shownotes") or raw.get("description") or ""),
        "image": image_url(raw.get("image")),
    }


def load_state(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {item["eid"]: item for item in data.get("episodes", [])}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def build_feed(podcast, episodes, show):
    title = podcast.get("title") or show["name"]
    podcast_url = show["url"]
    description = podcast.get("description") or f"{title} - 小宇宙播客"
    author = podcast.get("author") or title
    cover = image_url(podcast.get("image"))

    channel = ET.Element("channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = podcast_url
    ET.SubElement(channel, "description").text = description
    ET.SubElement(channel, "language").text = "zh-CN"
    ET.SubElement(channel, "lastBuildDate").text = email.utils.format_datetime(
        datetime.now(timezone.utc)
    )
    atom = ET.SubElement(channel, f"{{{NS['atom']}}}link")
    atom.set("href", show["feed_url"])
    atom.set("rel", "self")
    atom.set("type", "application/rss+xml")

    if cover:
        image = ET.SubElement(channel, "image")
        ET.SubElement(image, "url").text = cover
        ET.SubElement(image, "title").text = title
        ET.SubElement(image, "link").text = podcast_url
        ET.SubElement(channel, f"{{{NS['itunes']}}}image", {"href": cover})

    ET.SubElement(channel, f"{{{NS['itunes']}}}author").text = author
    ET.SubElement(channel, f"{{{NS['itunes']}}}summary").text = description
    ET.SubElement(channel, f"{{{NS['itunes']}}}explicit").text = "false"
    ET.SubElement(channel, f"{{{NS['itunes']}}}type").text = "episodic"

    for episode in episodes:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = episode["title"]
        ET.SubElement(item, "link").text = episode["url"]
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = episode["url"]
        ET.SubElement(item, "enclosure", {
            "url": episode["audio"],
            "length": str(episode.get("audio_length") or 0),
            "type": episode.get("audio_type") or "audio/mpeg",
        })
        pub = parse_date(episode.get("pub_date"))
        if pub:
            ET.SubElement(item, "pubDate").text = email.utils.format_datetime(pub)
        desc = episode.get("description") or ""
        ET.SubElement(item, "description").text = desc
        ET.SubElement(item, f"{{{NS['itunes']}}}summary").text = desc
        if episode.get("duration"):
            seconds = episode["duration"]
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            duration = (
                f"{hours:02d}:{minutes:02d}:{secs:02d}"
                if hours else f"{minutes:02d}:{secs:02d}"
            )
            ET.SubElement(item, f"{{{NS['itunes']}}}duration").text = duration
        if episode.get("image"):
            ET.SubElement(item, f"{{{NS['itunes']}}}image", {"href": episode["image"]})

    root = ET.Element("rss", {"version": "2.0"})
    root.append(channel)
    return ET.ElementTree(root)


def update_show(show):
    if show.get("platform") != "xiaoyuzhou":
        raise RuntimeError(f'Unsupported platform for {show.get("name")}: {show.get("platform")}')

    podcast, raw_episodes = fetch_source(show)
    state_path = Path(show["state_path"])
    output_path = Path(show["feed_path"])
    known = load_state(state_path)
    fresh = 0

    for raw in raw_episodes:
        episode = normalize_episode(raw)
        if not episode:
            continue
        old = known.get(episode["eid"], {})
        known[episode["eid"]] = {
            **old,
            **{key: value for key, value in episode.items() if value not in (None, "")},
        }
        if episode["eid"] not in old:
            fresh += 1

    if not known:
        raise RuntimeError(f'{show["name"]}: no usable episodes; refusing to publish an empty feed.')

    all_items = list(known.values())
    all_items.sort(
        key=lambda item: parse_date(item.get("pub_date"))
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    all_items = all_items[: int(show.get("max_episodes", 30))]

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {"podcast_id": podcast.get("pid"), "episodes": all_items},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_feed(podcast, all_items, show).write(
        output_path, encoding="utf-8", xml_declaration=True
    )
    print(
        f'{show["name"]}: published {len(all_items)} episodes; '
        f'discovered {fresh} new episode(s).'
    )
    print(f'  Feed: {show["feed_url"]}')
    print(f'  Newest: {all_items[0]["title"]}')


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    shows = config.get("podcasts") or []
    if not shows:
        raise RuntimeError("config.json contains no podcasts.")

    failures = []
    for show in shows:
        try:
            update_show(show)
        except Exception as exc:
            failures.append(f'{show.get("name", show.get("slug", "unknown"))}: {exc}')
            print(f"ERROR: {failures[-1]}", file=sys.stderr)

    if failures:
        raise RuntimeError(
            "One or more podcast feeds failed; no updates will be committed: "
            + " | ".join(failures)
        )


if __name__ == "__main__":
    main()
