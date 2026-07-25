# F4W Podcast Mass Downloader

Bulk-download podcasts and Wrestling Observer Newsletter issues from [F4W Online](https://www.f4wonline.com), organise them into a folder hierarchy by show/year/month, and (for podcasts) embed ID3 metadata tags automatically.

> **Note:** A valid F4W Online subscription is required.

---

## Installation

```bash
git clone https://github.com/your-username/F4WPodcastMassDownloader.git
cd F4WPodcastMassDownloader
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
| `--max-pages N` | — | Limit pages scraped per show (useful for testing) |
| `--no-yearly` | — | Don't create per-year sub-folders |
| `--no-monthly` | — | Don't create per-month sub-folders |
| `--page-delay SECS` | `1.0` | Sleep between index page requests |
| `--episode-delay SECS` | `0.5` | Sleep between episode page requests |
| `--overwrite` | — | Re-download files that already exist |
| `--dry-run` | — | Print what would be downloaded without downloading |

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
| `--max-pages N` | — | Limit archive pages scraped (useful for testing) |
| `--no-yearly` | — | Don't create per-year sub-folders |
| `--no-monthly` | — | Don't create per-month sub-folders |
| `--page-delay SECS` | `1.0` | Sleep between archive page requests |
| `--issue-delay SECS` | `0.5` | Sleep between individual issue requests |
| `--overwrite` | — | Re-download issues that already exist |
| `--dry-run` | — | Print what would be downloaded without downloading |

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

---

## Future ideas

- Keyword filter to selectively download episodes by title
- Interactive episode picker within a date range
- GUI / web front end
- `.mobi` output for the newsletter downloader (currently `.epub` only)
- Rename the distribution to something like `f4w-mass-downloader` now that it covers more than podcasts
