# Email to remarkable

Send an HTML, PDF, or PNG file by email and receive it on your Remarkable.

The Remarkable tablet is a great product, but I’ve always been frustrated by the lack of a feature to send content to my tablet via email.

I tinkered with a Python solution to address this gap. The code is quick and dirty, but it works for me and might help others too.

Feel free to share any improvement ideas!


## Requirements

To use this script, you need:
- The Remarkable tablet connected to the same network as the machine running the script.
- An SSH key configured on your Remarkable tablet.
- An API key from the html2pdfrocket.com service (free for up to 200 conversions per month).
- A MacOS or Linux terminal
- Create a dedicated email address for sending content to your Remarkable.

## How to use it ?

- Download the code.
- Fill in the config.cfg.sample file and rename it to config.cfg.
- Install the dependencies.
- Run main.py

You can let the script run; it will check every minute if your Remarkable tablet is connected and look for new content to fetch from your email inbox.

