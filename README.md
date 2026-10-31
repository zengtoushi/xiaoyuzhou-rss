# Xiaoyuzhou RSS

A personal RSS generator for multiple public Xiaoyuzhou podcasts.

## Published feeds

- **记意电波** — https://zengtoushi.github.io/xiaoyuzhou-rss/feeds/jiyi-radio.xml
- **越位线** — https://zengtoushi.github.io/xiaoyuzhou-rss/feeds/yueweixian.xml

Each feed retains up to 30 episodes. GitHub Actions refreshes all configured feeds every four hours. Audio files remain hosted by Xiaoyuzhou; this project publishes episode metadata and public audio enclosure links only. The public podcast page may expose only a recent batch of episodes on the first run; the saved history then accumulates as the scheduled refreshes discover new episodes. It does not perform a full historical backfill.

## Add a podcast

Add one entry to `config.json` with a unique `slug`, the public Xiaoyuzhou podcast URL, and unique `state_path`, `feed_path`, and `feed_url` values. Each podcast gets its own RSS file and episode history.

The parser currently reads the public podcast page's embedded `__NEXT_DATA__` data. The first workflow run is a compatibility test; if Xiaoyuzhou changes its page format or limits automated requests, the parser may need an update.

## Setup

In **Settings → Pages**, choose **GitHub Actions** as the source. Then run **Actions → Update podcast RSS and publish Pages → Run workflow** for the first fetch.
