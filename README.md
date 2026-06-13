# Email to reMarkable

Send content to your reMarkable — by email or by URL — and have it appear on
your tablet in a clean, e-ink-optimised layout.

The reMarkable tablet is a great product, but it lacks a built-in way to push
arbitrary web content to the device. This Python script bridges that gap: it
watches a dedicated mailbox (email mode) or reads a queue of URLs (URL mode),
converts the content to a well-formatted PDF and uploads it over the local
network.

## Features

### Email mode (default)

- **PDF attachments** are sent as-is.
- **PNG attachments** are converted to PDF (via Pillow).
- **HTML emails** (newsletters, articles…) are restyled with an academic,
  LaTeX-like layout optimized for e-ink reading, then converted to PDF via
  the html2pdfrocket.com API:
  - serif font (STIX Two by default — see `FONT` option), 16pt, justified text,
    single reading column;
  - everything forced to black & white, images grayscaled;
  - newsletter subheadings detected (large inline font-size) and restored as
    real headings;
  - hidden preheaders, tracking pixels, decorative separators and invisible
    padding removed;
  - a document header with subject, sender and date (in French).
- **Deduplication**: each processed email is recorded (SHA-256 hash) in
  `historique_file.txt` and never sent twice.
- **Mailbox cleanup**: emails are deleted from the POP3 server once the
  transfer to the tablet has succeeded (deletion is only committed when the
  POP3 session ends cleanly, so nothing is lost if the script crashes).

### URL mode (`--urls`)

Reads a list of URLs from `URLS_QUEUE.txt` (one URL per line), fetches each
page, strips away the noise (navigation menus, headers, footers, sidebars…)
and pushes the main article content to the tablet using the same academic PDF
style as email mode.

Boilerplate removal uses a cascade of four stages:

1. **lxml pre-processing** — runs before any extractor. If the page has an
   `<article>` or `<main>` tag, only that subtree is kept (everything else —
   navigation, sidebars, footer — is discarded at source). Otherwise `<nav>`,
   `<aside>`, `<footer>` and any element whose `class`/`id` contains a
   navigation keyword (menu, sidebar, cookie banner, ads, pagination…) are
   stripped from the document.
2. **trafilatura** — applied to the pre-processed HTML; purpose-built for news
   articles and blog posts, returns structured HTML and extracts the page title
   from Open Graph / meta tags.
3. **readability-lxml** — Mozilla Readability algorithm (the same engine behind
   Firefox's reader view), used as a fallback when trafilatura finds nothing.
4. **Pre-processed HTML** — last resort if both extractors fail; navigation has
   already been removed by step 1, so even this fallback is reasonably clean.

> **Note on paywalled or bot-protected sites** (e.g. Le Monde): these return
> an error page before any article content, so there is nothing to extract.
> The only workaround would be a headless browser with an authenticated
> session, which is out of scope for this script.

> **Note on Brotli-compressed sites**: some servers (e.g. Le Grand Continent)
> respond with Brotli (`br`) content encoding. The script deliberately advertises
> only `gzip, deflate` in its `Accept-Encoding` header so that servers always
> respond with a format that `requests` can decompress natively. Advertising `br`
> without the `brotli` package installed causes the raw compressed bytes to be
> passed through as text, resulting in a garbled PDF.

After processing, successfully sent URLs are removed from `URLS_QUEUE.txt`;
failed ones remain so the next run can retry them.

### Common

- **Automatic tablet discovery**: the reMarkable is located on the LAN by its
  MAC address (cached IP → ARP table → full subnet ping scan as a last resort).
- After new documents are uploaded, the xochitl service is restarted over SSH
  so they appear in the tablet's library.

## Requirements

- The reMarkable tablet connected to the same network as the machine running
  the script.
- An SSH key configured on your reMarkable tablet (the script uses
  `scp`/`ssh` as `root`).
- An API key from the html2pdfrocket.com service (free for up to 200
  conversions per month). Several keys can be configured (separated by `;`);
  they are tried in random order, and the next one is automatically used when
  the current one has reached its monthly limit.
- A macOS or Linux machine.
- A dedicated email address (POP3 with SSL) used only for sending content to
  your reMarkable.

## How to use it

1. Download the code.
2. Install the dependencies: `pip install -r requirements.txt`
3. Copy `config.cfg.sample` to `config.cfg` and fill it in:

   | Option | Description |
   |---|---|
   | `REMARKABLE_MAC` | MAC address of the tablet (Settings → Help → About) |
   | `HOST` / `USER` / `PASSWORD` | POP3-SSL credentials of the dedicated mailbox (port 995) |
   | `API_KEY` | html2pdfrocket key(s), `;`-separated |
   | `CHECK_INTERVAL` | seconds between two mailbox checks (default: 600) |
   | `FONT` | PDF font: `stix-two` (default), `latin-modern`, `eb-garamond`, `crimson`, `georgia` |

4. Run the script:

   ```bash
   # Email mode — polls the mailbox every CHECK_INTERVAL seconds (infinite loop)
   python3 main.py

   # URL mode — processes URLS_QUEUE.txt once and exits
   python3 main.py --urls
   ```

   **`URLS_QUEUE.txt` format**: one URL per line, lines not starting with
   `http` are ignored (empty lines, comments).

   ```
   https://example.com/article-one
   https://example.com/article-two
   ```

Let the script run: on every cycle it checks whether the tablet is reachable,
fetches new emails, converts them and uploads them. The detected IP of the
tablet is cached in `config.cfg` (`REMARKABLE_IP`) to avoid rescanning the
network at each cycle.

Feel free to share any improvement ideas!
