# F4W Archive Downloader

Bulk-download podcasts and Wrestling Observer Newsletter issues from [F4W Online](https://www.f4wonline.com), organise them into a folder hierarchy by show/year/month, and (for podcasts) embed ID3 metadata tags automatically.

> **Note:** A valid F4W Online subscription is required.

---

## Installation

```bash
git clone https://github.com/ir47/f4w-archive-downloader.git
cd f4w-archive-downloader
pip install -e .
```

This installs the `f4w-download` and `f4w-newsletters` commands and all dependencies.

Alternatively, install dependencies directly without packaging:

```bash
pip install -r requirements.txt
```

Then run via `python -m podcastDownloader.runner` or `python -m newsletterDownloader.runner`.

`f4w-newsletters --format kindle` additionally requires [Calibre](https://calibre-ebook.com/download) to be installed separately (it is not a pip package) with its `ebook-convert` command on your `PATH`.

---

## Credentials

Both commands share one F4W Online login. Credentials are resolved in this order:

1. The `F4W_USERNAME` and `F4W_PASSWORD` environment variables — both must be set, or the pair is ignored.
2. An interactive prompt (the password is hidden).

Setting the environment variables is useful for unattended runs:

```bash
export F4W_USERNAME="you@example.com"
export F4W_PASSWORD="your-password"
f4w-download --all
```

Nothing auto-loads a `.env` file — there is no `python-dotenv` dependency — so if you keep credentials in one, source it yourself first:

```bash
set -a; . ./.env; set +a
```

`.env` is gitignored. Never commit real credentials.

---

## Usage

```bash
# List all available show slugs
f4w-download --list-shows

# Download all Wrestling Observer Radio episodes
f4w-download --show wrestling-observer-radio

# Download a specific show between two dates
f4w-download --show bryan-and-vinny-show --start "January 1, 2025" --end "March 17, 2026"

# Dry run — see what would be downloaded without downloading anything
f4w-download --show wrestling-observer-radio --max-pages 1 --dry-run

# Download all shows to a custom folder without monthly sub-folders
f4w-download --all --output ~/Podcasts --no-monthly

# Re-download episodes that already exist on disk
f4w-download --show after-dark --overwrite
```

### All options

| Flag | Default | Description |
|---|---|---|
| `--show SLUG` | — | Download one show by slug (mutually exclusive with `--all`) |
| `--all` | — | Download every show |
| `--list-shows` | — | Print available show slugs and exit |
| `--output PATH` | `~/Downloads/F4WPodcasts` | Root download directory |
| `--start DATE` | — | Only episodes on or after this date (`January 1, 2025`) |
| `--end DATE` | — | Only episodes on or before this date |
| `--max-pages N` | — | Limit archive index pages scraped (useful for testing) |
| `--no-yearly` | — | Don't create per-year sub-folders |
| `--no-monthly` | — | Don't create per-month sub-folders |
| `--page-delay SECS` | `1.0` | Sleep between archive index page requests |
| `--item-delay SECS` | `0.5` | Sleep between episode page requests |
| `--overwrite` | — | Re-download files that already exist |
| `--dry-run` | — | Print what would be downloaded without downloading |

> `--episode-delay` is still accepted as an alias for `--item-delay`, which replaced it when the two downloaders were unified onto one CLI.

---

## Output structure

```
~/Downloads/F4WPodcasts/
└── Wrestling Observer Radio/
    └── 2025/
        └── March/
            └── 17-Episode Title.mp3
```

---

## Newsletter Downloader

Bulk-download Wrestling Observer Newsletter issues from `members.f4wonline.com`, using the same F4W login as the podcast downloader.

```bash
# Download all newsletter issues as PDFs
f4w-newsletters --format pdf

# Download issues between two dates as saved webpages
f4w-newsletters --format html --start "January 1, 2025" --end "March 17, 2026"

# Dry run — see what would be downloaded without downloading anything
f4w-newsletters --format pdf --max-pages 1 --dry-run

# Convert issues to Kindle-ready .epub files (requires Calibre installed)
f4w-newsletters --format kindle --output ~/Newsletters
```

### All options

| Flag | Default | Description |
|---|---|---|
| `--format {pdf,html,kindle}` | `pdf` | Save the original PDF, the raw scraped webpage, or a Calibre-converted Kindle ebook |
| `--output PATH` | `~/Downloads/F4WNewsletters` | Root download directory |
| `--start DATE` | — | Only issues on or after this date (`January 1, 2025`) |
| `--end DATE` | — | Only issues on or before this date |
| `--max-pages N` | — | Limit archive index pages scraped (useful for testing) |
| `--no-yearly` | — | Don't create per-year sub-folders |
| `--no-monthly` | — | Don't create per-month sub-folders |
| `--page-delay SECS` | `1.0` | Sleep between archive index page requests |
| `--item-delay SECS` | `0.5` | Sleep between individual issue requests |
| `--overwrite` | — | Re-download issues that already exist |
| `--dry-run` | — | Print what would be downloaded without downloading |

> `--issue-delay` is still accepted as an alias for `--item-delay`, which replaced it when the two downloaders were unified onto one CLI.

### Output structure

```
~/Downloads/F4WNewsletters/
└── Wrestling Observer Newsletter/
    └── 2026/
        └── July/
            └── 13-July 13, 2026 Observer Newsletter.pdf
```

---

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

325 tests, no network access required — every HTTP call is mocked.

### Project structure

Both downloaders are thin site-specific shells over a shared core. Anything not
specific to podcasts or newsletters lives in `f4wCommon`:

```
f4wCommon/            shared core — site-agnostic
├── auth.py           login flow, form-field detection, credential resolution
├── cli.py            the argument set both CLIs share, plus login_or_exit()
├── dates.py          date formats, parsing, enrichment, range filtering
├── fsutil.py         filename sanitising, output path/filename building
├── http.py           session, retrying fetch, resumable streaming download
├── pipeline.py       the download workflow: dry-run, loop, summary
└── scrape.py         WordPress archive helpers: listing pages, pagination

podcastDownloader/    episode scraping, MP3 download, ID3 tagging
newsletterDownloader/ issue scraping, PDF/HTML saving, Calibre conversion
```

A downloader supplies a **format handler** with the signature
`(item, details, dest, session) -> bool`, and `f4wCommon.pipeline` drives the
rest — resolving destinations, honouring skip/overwrite, fetching detail pages,
and tallying results. Adding an output format means writing one handler and
registering it, not another loop.

---

## Future ideas

- Keyword filter to selectively download episodes by title
- Interactive episode picker within a date range
- GUI / web front end
- `.mobi` output for the newsletter downloader (currently `.epub` only)
