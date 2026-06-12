# Email to reMarkable

Send an HTML, PDF, or PNG file by email and receive it on your reMarkable.

The reMarkable tablet is a great product, but I've always been frustrated by the lack of a feature to send content to my tablet via email.

This Python script bridges that gap: it watches a dedicated mailbox and pushes everything it receives to the tablet over the local network.

## Features

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
- **Automatic tablet discovery**: the reMarkable is located on the LAN by its
  MAC address (cached IP → ARP table → full subnet ping scan as a last resort).
- **Deduplication**: each processed email is recorded (SHA-256 hash) in
  `historique_file.txt` and never sent twice.
- **Mailbox cleanup**: emails are deleted from the POP3 server once the
  transfer to the tablet has succeeded (deletion is only committed when the
  POP3 session ends cleanly, so nothing is lost if the script crashes).
- After new documents are uploaded, the xochitl service is restarted over SSH
  so they appear in the tablet's library.

## Requirements

- The reMarkable tablet connected to the same network as the machine running
  the script.
- An SSH key configured on your reMarkable tablet (the script uses
  `scp`/`ssh` as `root`).
- An API key from the html2pdfrocket.com service (free for up to 200
  conversions per month). Several keys can be configured (separated by `;`),
  one is picked at random for each conversion.
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

4. Run `python3 main.py`

Let the script run: on every cycle it checks whether the tablet is reachable,
fetches new emails, converts them and uploads them. The detected IP of the
tablet is cached in `config.cfg` (`REMARKABLE_IP`) to avoid rescanning the
network at each cycle.

Feel free to share any improvement ideas!
