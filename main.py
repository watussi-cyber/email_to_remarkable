import argparse
import subprocess
from email.header import decode_header
import platform
import time
from email.parser import Parser
import poplib
from PIL import Image
from datetime import datetime, UTC
import json
import requests
import os
import glob
import hashlib
import uuid
import configparser
import random
import re
import socket
import concurrent.futures

config = configparser.ConfigParser()
config.read("config.cfg")

REMARKABLE_MAC = config.get('PROD', 'REMARKABLE_MAC').lower()

HOST = config.get('PROD', 'HOST')
PORT = 995
USER = config.get('PROD', 'USER')
PASSWORD = config.get('PROD', 'PASSWORD')

# Compatible avec API_KEYS (main.py) et API_KEY (config.cfg.sample)
_raw_keys = config.get('PROD', 'API_KEYS', fallback='') or config.get('PROD', 'API_KEY', fallback='')
API_KEYS = [k.strip() for k in _raw_keys.split(";") if k.strip()]

# Intervalle entre deux relèves de la boîte mail (secondes)
CHECK_INTERVAL = config.getint('PROD', 'CHECK_INTERVAL', fallback=600)


# Feuille de style "académique" appliquée aux emails HTML avant conversion PDF.
# Pensée pour l'écran e-ink de la reMarkable : noir et blanc, police serif
# type LaTeX (Computer Modern / Latin Modern), texte justifié avec césure,
# interligne généreux.
# Polices type LaTeX chargées en webfont par le convertisseur.
# Sélection via l'option FONT de config.cfg (défaut : stix-two).
FONT_PRESETS = {
	# TTF servi par jsDelivr : seul format que wkhtmltopdf charge à coup sûr
	'latin-modern': (
		"""@font-face { font-family: 'Latin Modern'; font-weight: normal; font-style: normal;
	src: url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-regular.ttf') format('truetype'); }
@font-face { font-family: 'Latin Modern'; font-weight: bold; font-style: normal;
	src: url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-bold.ttf') format('truetype'); }
@font-face { font-family: 'Latin Modern'; font-weight: normal; font-style: italic;
	src: url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-italic.ttf') format('truetype'); }
@font-face { font-family: 'Latin Modern'; font-weight: bold; font-style: italic;
	src: url('https://cdn.jsdelivr.net/gh/vincentdoerig/latex-css@1.10.0/fonts/LM-bold-italic.ttf') format('truetype'); }""",
		'"Latin Modern", Georgia, "Times New Roman", serif'),
	'stix-two': (
		"@import url('https://fonts.googleapis.com/css2?family=STIX+Two+Text:ital,wght@0,400;0,700;1,400;1,700&display=swap');",
		'"STIX Two Text", Georgia, "Times New Roman", serif'),
	'eb-garamond': (
		"@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,700;1,400;1,700&display=swap');",
		'"EB Garamond", Georgia, "Times New Roman", serif'),
	'crimson': (
		"@import url('https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,700;1,400;1,700&display=swap');",
		'"Crimson Text", Georgia, "Times New Roman", serif'),
	'georgia': ('', 'Georgia, "Times New Roman", serif'),
}

ACADEMIC_CSS = """
__FONT_IMPORT__
@page { margin: 0; }
* {
	background: #ffffff !important;
	color: #000000 !important;
	box-shadow: none !important;
	text-shadow: none !important;
}
html {
	font-size: 16pt;
}
body {
	font-family: __FONT_FAMILY__;
	line-height: 1.55;
	margin: 0 auto;
	padding: 1.2cm 1.4cm;
	max-width: 16cm;
	text-align: justify;
	hyphens: auto;
	-webkit-hyphens: auto;
	overflow-wrap: break-word;
	word-wrap: break-word;
}
div { max-width: 100% !important; }
h1, h2, h3, h4, h5, h6 {
	font-family: inherit;
	font-weight: bold;
	text-align: left;
	line-height: 1.25;
	margin: 1.4em 0 0.6em 0;
	page-break-after: avoid;
}
h1 { font-size: 1.7em; }
h2 { font-size: 1.4em; }
h3 { font-size: 1.15em; }
/* Intertitres détectés dans les newsletters (grande font-size inline) */
[data-acad-h] {
	display: block !important;
	font-weight: bold !important;
	text-align: left !important;
	line-height: 1.25 !important;
	margin: 1.3em 0 0.5em 0 !important;
	page-break-after: avoid;
	text-decoration: none !important;
}
[data-acad-h="2"] { font-size: 1.4em !important; }
[data-acad-h="3"] { font-size: 1.15em !important; }
h4, h5, h6 { font-size: 1em; font-style: italic; }
p {
	margin: 0 0 0.7em 0;
}
a {
	color: #000000 !important;
	text-decoration: underline;
}
img {
	max-width: 100% !important;
	height: auto !important;
	filter: grayscale(100%);
	display: block;
	margin: 0.8em auto;
}
blockquote {
	margin: 0.8em 0 0.8em 1.2em;
	padding-left: 0.8em;
	border-left: 2pt solid #000000;
	font-style: italic;
}
ul, ol {
	margin: 0.5em 0 0.8em 0;
	padding-left: 1.6em;
}
li { margin-bottom: 0.25em; }
/* Les emails utilisent des tableaux pour la mise en page : on les linéarise
   en blocs sans bordure pour obtenir une colonne de lecture unique. */
table, thead, tbody, tfoot, tr, th, td {
	display: block !important;
	width: auto !important;
	max-width: 100% !important;
	border: none !important;
	padding: 0 !important;
	margin: 0 !important;
	text-align: justify;
}
td, th { margin-bottom: 0.3em !important; }
th { font-weight: bold; }
pre, code, kbd, samp {
	font-family: "Latin Modern Mono", "Courier New", monospace;
	font-size: 0.88em;
}
pre {
	white-space: pre-wrap;
	border: 0.5pt solid #000000;
	padding: 0.6em;
	margin: 0.8em 0;
}
hr {
	border: none;
	border-top: 0.5pt solid #000000;
	margin: 1.2em 0;
}
.email-header {
	font-size: 0.85em;
	border-bottom: 1pt solid #000000;
	padding-bottom: 0.6em;
	margin-bottom: 1.4em;
	text-align: left;
}
.email-header .email-subject {
	font-size: 1.5em;
	font-weight: bold;
	display: block;
	margin-bottom: 0.3em;
}
"""


FRENCH_DAYS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
FRENCH_MONTHS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']


def format_date_fr(date_header):
	"""Convertit l'en-tête Date RFC 2822 en date lisible en français."""
	if not date_header:
		return ''
	try:
		from email.utils import parsedate_to_datetime
		dt = parsedate_to_datetime(date_header)
		return f"{FRENCH_DAYS[dt.weekday()]} {dt.day} {FRENCH_MONTHS[dt.month - 1]} {dt.year}, {dt:%H:%M}"
	except Exception as e:
		print(f"[DEBUG] format_date_fr() échec parsing '{date_header}': {e}")
		return date_header


def apply_academic_style(html_content, subject=None, sender=None, date=None, font=None):
	"""Nettoie le HTML de l'email et applique la feuille de style académique."""
	print(f"[DEBUG] apply_academic_style() appelé, longueur HTML={len(html_content)} caractères")

	font = font or config.get('PROD', 'FONT', fallback='stix-two')
	font_import, font_family = FONT_PRESETS.get(font, FONT_PRESETS['georgia'])
	print(f"[DEBUG] Police sélectionnée: {font}")
	css = ACADEMIC_CSS.replace('__FONT_IMPORT__', font_import).replace('__FONT_FAMILY__', font_family)

	# Suppression des éléments cachés (préheaders de newsletters, etc.)
	# AVANT de retirer les attributs style, sinon ils deviennent visibles
	hidden_pattern = r'display\s*:\s*none|visibility\s*:\s*hidden|max-height\s*:\s*0'
	for tag in ('div', 'span', 'p', 'td'):
		html_content = re.sub(
			rf'<{tag}\b[^>]*style\s*=\s*["\'][^"\']*(?:{hidden_pattern})[^"\']*["\'][^>]*>(?:(?!</?{tag}\b).)*?</{tag}>',
			'', html_content, flags=re.IGNORECASE | re.DOTALL)

	# Pixels de tracking, espaceurs et séparateurs décoratifs :
	# toute image dont une dimension fait 8 px ou moins
	html_content = re.sub(r'<img\b[^>]*\b(?:width|height)\s*=\s*(?:["\']0*[1-8](?:px)?["\']|0*[1-8](?:px)?(?=[\s>]))[^>]*/?>', '', html_content, flags=re.IGNORECASE)
	# Commentaires HTML, y compris les conditionnels Outlook <!--[if mso]>...
	html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)
	# Bourrage invisible des préheaders : longues séries de &zwnj;/&nbsp;/&shy;
	html_content = re.sub(r'(?:&(?:zwnj|nbsp|shy|#8204|#173|#847|#65279);\s*){4,}', ' ', html_content, flags=re.IGNORECASE)

	# Détection des intertitres AVANT le nettoyage des styles : les newsletters
	# n'utilisent pas <h1>-<h6> mais des span/td/p avec une grande font-size.
	# On les marque avec un attribut data-acad-h que la CSS stylise en titre.
	def _tag_heading(m):
		size = float(m.group('size'))
		if m.group('unit').lower() == 'pt':
			size *= 4 / 3
		if size >= 23:
			level = '2'
		elif size >= 17:
			level = '3'
		else:
			return m.group(0)
		return f'<{m.group("tag")} data-acad-h="{level}"{m.group("attrs")}>'

	html_content = re.sub(
		r'<(?P<tag>span|td|p|div|a)\b(?P<attrs>[^>]*style\s*=\s*["\'][^"\']*font-size\s*:\s*(?P<size>[\d.]+)\s*(?P<unit>px|pt)[^"\']*["\'][^>]*)>',
		_tag_heading, html_content, flags=re.IGNORECASE)

	# Suppression des éléments qui peuvent faire planter wkhtmltopdf :
	# scripts, iframes, objects, embeds — ils ne produisent rien d'utile dans un PDF
	for dangerous_tag in ('script', 'noscript', 'iframe', 'object', 'embed'):
		html_content = re.sub(rf'<{dangerous_tag}\b[^>]*>.*?</{dangerous_tag}>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
		html_content = re.sub(rf'<{dangerous_tag}\b[^>]*/>', '', html_content, flags=re.IGNORECASE)

	# Suppression des styles existants pour éviter les conflits :
	# blocs <style>, feuilles externes <link rel=stylesheet>, attributs de présentation
	html_content = re.sub(r'<style\b[^>]*>.*?</style>', '', html_content, flags=re.IGNORECASE | re.DOTALL)
	html_content = re.sub(r'<link\b[^>]*rel=["\']?stylesheet["\']?[^>]*>', '', html_content, flags=re.IGNORECASE)
	html_content = re.sub(r'\sstyle\s*=\s*"[^"]*"', '', html_content, flags=re.IGNORECASE)
	html_content = re.sub(r"\sstyle\s*=\s*'[^']*'", '', html_content, flags=re.IGNORECASE)
	html_content = re.sub(r'\s(?:bgcolor|background|color|face|align|width|height)\s*=\s*"[^"]*"', '', html_content, flags=re.IGNORECASE)
	html_content = re.sub(r"\s(?:bgcolor|background|color|face|align|width|height)\s*=\s*'[^']*'", '', html_content, flags=re.IGNORECASE)
	# Les emails marketing utilisent souvent des images de tracking 1x1 et des <font>
	html_content = re.sub(r'</?font[^>]*>', '', html_content, flags=re.IGNORECASE)

	# Suppression des espaceurs verticaux : séries de <br> et éléments vides
	# (les newsletters utilisent des cellules/divs vides pour créer du blanc)
	html_content = re.sub(r'(?:<br\b[^>]*/?>\s*){2,}', '<br>', html_content, flags=re.IGNORECASE)
	empty_el = r'<(p|div|span|td|th|tr|tbody|thead|table|center)\b[^>]*>(?:\s|&nbsp;|&#160;|<br\b[^>]*/?>)*</\1>'
	for _ in range(5):
		cleaned = re.sub(empty_el, '', html_content, flags=re.IGNORECASE)
		if cleaned == html_content:
			break
		html_content = cleaned

	# Extraction du contenu du <body> si le document est complet
	body_match = re.search(r'<body\b[^>]*>(.*?)</body>', html_content, flags=re.IGNORECASE | re.DOTALL)
	body = body_match.group(1) if body_match else html_content

	# En-tête type article : sujet, expéditeur, date
	header_html = ""
	if subject or sender or date:
		header_parts = []
		if subject:
			header_parts.append(f'<span class="email-subject">{subject}</span>')
		if sender:
			header_parts.append(f'{sender}')
		if date:
			header_parts.append(f' &mdash; {date}')
		header_html = f'<div class="email-header">{"".join(header_parts)}</div>'

	styled = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<style>{css}</style>
</head>
<body>
{header_html}
{body}
</body>
</html>"""
	print(f"[DEBUG] HTML stylisé, nouvelle longueur={len(styled)} caractères")
	return styled


def png_to_pdf(png_path, pdf_path):
	print(f"[DEBUG] png_to_pdf() appelé : {png_path} -> {pdf_path}")
	try:
		with Image.open(png_path) as img:
			print(f"[DEBUG] Image ouverte, mode={img.mode}, size={img.size}")
			if img.mode in ("RGBA", "P"):
				print(f"[DEBUG] Conversion du mode {img.mode} -> RGB")
				img = img.convert("RGB")
			img.save(pdf_path, "PDF")
		print(f"PNG converti en PDF avec succès : {pdf_path}")
	except Exception as e:
		print(f"Erreur lors de la conversion PNG en PDF : {e}")


def decode_mime_subject(encoded_subject):
	print(f"[DEBUG] decode_mime_subject() appelé, sujet brut : {encoded_subject[:80] if encoded_subject else 'None'}...")
	if not encoded_subject:
		return "Sans sujet"
	decoded_parts = decode_header(encoded_subject)
	subject = ""
	for part, encoding in decoded_parts:
		if isinstance(part, bytes):
			subject += part.decode(encoding or 'utf-8', errors='ignore')
		else:
			subject += part
	print(f"[DEBUG] Sujet décodé : {subject[:80]}")
	return subject


def _arp_lookup(mac):
	print(f"[DEBUG] _arp_lookup() cherche MAC: {mac}")
	try:
		if platform.system().lower() == "linux":
			result = subprocess.run(["ip", "neigh", "show"], capture_output=True, text=True, timeout=10)
			for line in result.stdout.splitlines():
				if mac in line.lower():
					print(f"[DEBUG] MAC trouvée dans ARP: {line.strip()}")
					match = re.match(r'^(\d+\.\d+\.\d+\.\d+)\s', line)
					if match:
						return match.group(1)
		else:
			result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
			for line in result.stdout.splitlines():
				if mac in line.lower():
					print(f"[DEBUG] MAC trouvée dans ARP: {line.strip()}")
					match = re.search(r'\((\d+\.\d+\.\d+\.\d+)\)', line)
					if match:
						return match.group(1)
	except Exception as e:
		print(f"[DEBUG] _arp_lookup() exception: {e}")
	print("[DEBUG] _arp_lookup() : MAC non trouvée")
	return None


def _get_local_subnet():
	print("[DEBUG] _get_local_subnet() : détection du sous-réseau local...")
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.connect(("8.8.8.8", 80))
		local_ip = s.getsockname()[0]
	finally:
		s.close()
	subnet = '.'.join(local_ip.split('.')[:3])
	print(f"[DEBUG] Sous-réseau: {subnet}.0/24")
	return subnet


def _ping_host(ip):
	os_type = platform.system().lower()
	if os_type == "darwin":
		cmd = ["ping", "-c", "3", "-W", "1000", ip]
	else:
		cmd = ["ping", "-c", "3", "-W", "1", ip]
	try:
		subprocess.run(cmd, capture_output=True, timeout=10)
	except subprocess.TimeoutExpired:
		pass


def _save_cached_ip(ip):
	cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.cfg')
	with open(cfg_path, 'r') as f:
		content = f.read()
	if re.search(r'REMARKABLE_IP\s*[=:]', content):
		content = re.sub(r'REMARKABLE_IP\s*[=:]\s*[\d.]*', f'REMARKABLE_IP : {ip}', content)
	else:
		content = content.replace('[PROD]', f'[PROD]\nREMARKABLE_IP : {ip}', 1)
	with open(cfg_path, 'w') as f:
		f.write(content)
	config.set('PROD', 'REMARKABLE_IP', ip)


def find_remarkable_ip(mac):
	print(f"[DEBUG] find_remarkable_ip() démarrage pour MAC={mac}")
	# 1. Essai sur la dernière IP connue (évite le scan complet)
	cached_ip = config.get('PROD', 'REMARKABLE_IP', fallback='').strip()
	if cached_ip:
		print(f"[DEBUG] IP en cache trouvée: {cached_ip}, test avec ping...")
		_ping_host(cached_ip)
		if _arp_lookup(mac) == cached_ip:
			print(f"[DEBUG] IP cache confirmée: {cached_ip}")
			return cached_ip
		print("[DEBUG] IP cache non confirmée, passage à l'étape 2")

	# 2. Vérification du cache ARP complet
	ip = _arp_lookup(mac)
	if ip:
		print(f"[DEBUG] IP trouvée via ARP: {ip}, sauvegarde...")
		_save_cached_ip(ip)
		return ip

	# 3. Scan complet du sous-réseau
	print("reMarkable not in ARP cache, scanning network...")
	subnet = _get_local_subnet()
	print(f"[DEBUG] Début scan du sous-réseau {subnet}.0/24 (254 hôtes, max 50 workers)...")
	start_scan = time.time()
	with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
		futures = [executor.submit(_ping_host, f"{subnet}.{i}") for i in range(1, 255)]
		concurrent.futures.wait(futures, timeout=30)
	print(f"[DEBUG] Scan terminé en {time.time() - start_scan:.1f}s")
	ip = _arp_lookup(mac)
	if ip:
		print(f"[DEBUG] IP trouvée après scan: {ip}")
		_save_cached_ip(ip)
	else:
		print("[DEBUG] IP non trouvée après scan complet")
	return ip


def ping_ip(ip_address, timeout=5):
	print(f"[DEBUG] ping_ip() : ping {ip_address} (timeout={timeout}s)")
	os_type = platform.system().lower()
	if os_type == "darwin":
		command = ["ping", "-c", "1", "-W", str(timeout * 1000), ip_address]
	elif os_type == "linux":
		command = ["ping", "-c", "1", "-W", str(timeout), ip_address]
	else:
		raise OSError("OS not supported. Use MacOS or Linux.")

	try:
		result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
		success = result.returncode == 0
		print(f"[DEBUG] ping_ip() résultat: {'OK' if success else 'ÉCHEC'}")
		return success
	except subprocess.TimeoutExpired:
		print(f"[DEBUG] ping_ip() timeout expiré pour {ip_address}")
		return False
	except Exception as e:
		print(f"Ping error: {str(e)}")
		return False


_BLACKLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.api_key_blacklist.json')
_BLACKLIST_DURATION = 24 * 3600


def _blacklist_load():
	try:
		with open(_BLACKLIST_FILE) as f:
			return json.load(f)
	except (FileNotFoundError, json.JSONDecodeError):
		return {}


def _blacklist_add(api_key):
	bl = _blacklist_load()
	bl[api_key] = time.time()
	with open(_BLACKLIST_FILE, 'w') as f:
		json.dump(bl, f)
	print(f"[DEBUG] Clé {api_key[:8]}... blacklistée pour 24h")


def _blacklist_active(api_key):
	bl = _blacklist_load()
	ts = bl.get(api_key)
	if ts is None:
		return False
	elapsed = time.time() - ts
	if elapsed < _BLACKLIST_DURATION:
		print(f"[DEBUG] Clé {api_key[:8]}... blacklistée encore {(_BLACKLIST_DURATION - elapsed) / 3600:.1f}h — ignorée")
		return True
	# Expirée : on la retire
	del bl[api_key]
	with open(_BLACKLIST_FILE, 'w') as f:
		json.dump(bl, f)
	return False


def _html_to_pdf_local(html_content, output_pdf):
	"""Fallback local via Playwright/Chromium quand toutes les clés API sont épuisées."""
	try:
		from playwright.sync_api import sync_playwright
	except ImportError:
		print("[ERROR] playwright non installé. Lancez : py -m pip install playwright && py -m playwright install chromium")
		return False
	try:
		print("[DEBUG] Fallback Playwright/Chromium local")
		with sync_playwright() as p:
			browser = p.chromium.launch()
			page = browser.new_page()
			page.set_content(html_content, wait_until="domcontentloaded")
			page.pdf(path=output_pdf, format="A4", print_background=True,
			         margin={"top": "8mm", "bottom": "8mm", "left": "5mm", "right": "5mm"})
			browser.close()
		if os.path.exists(output_pdf) and os.path.getsize(output_pdf) > 0:
			print(f"[DEBUG] Fallback Playwright réussi : {output_pdf}")
			return True
		print("[ERROR] Fallback Playwright : fichier vide ou absent")
		return False
	except Exception as e:
		print(f"[ERROR] Fallback Playwright : {e}")
		return False


def html_to_pdf(api_keys, html_content, output_pdf):
	print(f"[DEBUG] html_to_pdf() appelé, longueur HTML={len(html_content)} caractères, output={output_pdf}")
	api_url = "https://api.html2pdfrocket.com/pdf"

	if isinstance(api_keys, str):
		api_keys = [api_keys]

	keys_to_try = [k for k in api_keys if not _blacklist_active(k)]
	random.shuffle(keys_to_try)

	if not keys_to_try:
		print("[DEBUG] Toutes les clés sont blacklistées — passage direct au fallback local.")

	for api_key in keys_to_try:
		data = {
			"apikey": api_key,
			"value": html_content,
			# Mise en page : les marges sont gérées par le CSS (padding du body),
			# on réduit donc celles du convertisseur au minimum.
			"PageSize": "A4",
			"MarginLeft": "5",
			"MarginRight": "5",
			"MarginTop": "8",
			"MarginBottom": "8",
			"UseGrayscale": "true",
			# Sans cela wkhtmltopdf rétrécit la page pour faire tenir les
			# layouts larges -> police minuscule sur la reMarkable
			"EnableSmartShrinking": "false",
		}
		try:
			print(f"[DEBUG] Envoi requête API html2pdfrocket (clé={api_key[:8]}..., HTML={len(data['value'])} chars)")
			response = requests.post(api_url, data=data, timeout=120)
			print(f"[DEBUG] Réponse API: status={response.status_code}, taille={len(response.content)} octets")
			if response.status_code == 200:
				if not response.content.startswith(b'%PDF'):
					print(f"[ERROR] Réponse non-PDF reçue (clé={api_key[:8]}...): {response.content[:300]}")
					continue
				with open(output_pdf, 'wb') as pdf_file:
					pdf_file.write(response.content)
				print(f"PDF conversion successful : {output_pdf}")
				return True
			print(f"Error during PDF conversion (clé={api_key[:8]}...): {response.status_code} - {response.text}")
			if response.status_code == 400 and "monthly volume limit" in response.text:
				_blacklist_add(api_key)
				continue
			# Autre erreur HTTP : on blackliste aussi pour éviter les appels inutiles
			_blacklist_add(api_key)
		except Exception as e:
			print(f"Error : {e}")
			_blacklist_add(api_key)
		continue

	print("[ERROR] API html2pdfrocket indisponible pour toutes les clés — tentative fallback local.")
	return _html_to_pdf_local(html_content, output_pdf)


def cleanup_uuid_files(content_uuid):
	"""Supprime uniquement les fichiers temporaires de ce document (pas de rm *)."""
	for path in glob.glob(f"{content_uuid}*"):
		try:
			os.remove(path)
			print(f"[DEBUG] Fichier temporaire supprimé: {path}")
		except OSError as e:
			print(f"[DEBUG] Impossible de supprimer {path}: {e}")


def process_message(msg, list_hash, historique_file, remarkable_ip):
	"""Traite un email : extraction, conversion en PDF, envoi SCP.
	Retourne 'sent' si le document a été envoyé sur la reMarkable,
	'duplicate' s'il avait déjà été traité lors d'un cycle précédent,
	False en cas d'échec ou de contenu inexploitable."""
	content_uuid = uuid.uuid4()
	print(f"[DEBUG] UUID généré: {content_uuid}")
	msg_content = b'\r\n'.join(msg[1])
	print(f"[DEBUG] Taille du message brut: {len(msg_content)} octets")
	message_hash = hashlib.sha256(msg_content).hexdigest()

	if message_hash in list_hash:
		print(f"Email already processed : {message_hash}")
		return 'duplicate'
	print(f"Hash : {message_hash}")

	email_message = Parser().parsestr(msg_content.decode('utf-8', errors='ignore'))
	visible_name = decode_mime_subject(email_message['subject'])
	print(f"Email subject : {visible_name}")
	print(f"[DEBUG] Content-Type: {email_message.get_content_type()}, is_multipart: {email_message.is_multipart()}")

	pdf_found = False
	png_found = False
	html_content = None
	pdf_path = f"{content_uuid}.pdf"

	parts = email_message.walk() if email_message.is_multipart() else [email_message]
	for part in parts:
		ct = part.get_content_type()
		cd = part.get('Content-Disposition')
		print(f"[DEBUG] Partie: type={ct}, disposition={cd}")
		filename = part.get_filename()

		if ct == 'image/png' and cd is not None and filename and filename.lower().endswith('.png'):
			print('PNG found')
			png_found = True
			attachment = part.get_payload(decode=True)
			print(f"[DEBUG] Taille pièce jointe PNG décodée: {len(attachment)} octets")
			png_path = f"{content_uuid}.png"
			with open(png_path, 'wb') as f:
				f.write(attachment)
			print(f"PNG downloaded : {png_path}")
			png_to_pdf(png_path, pdf_path)
			os.remove(png_path)
			visible_name = filename

		elif part.get_content_maintype() == 'application' and cd is not None and filename and filename.lower().endswith('.pdf'):
			print('PDF found')
			pdf_found = True
			attachment = part.get_payload(decode=True)
			print(f"[DEBUG] Taille PDF décodé: {len(attachment)} octets")
			visible_name = filename
			with open(pdf_path, 'wb') as f:
				f.write(attachment)
			print(f"PDF download successful : {pdf_path}")

		elif ct == "text/html" and html_content is None:
			raw_html = part.get_payload(decode=True)
			charset = part.get_content_charset()
			print(f"[DEBUG] Partie HTML trouvée, charset={charset}, taille brute={len(raw_html) if raw_html else 0}")
			if raw_html:
				print('HTML content found')
				html_content = raw_html.decode(charset or 'utf-8', errors='ignore')

	print(f"[DEBUG] Résumé: pdf_found={pdf_found}, png_found={png_found}, html_content={'oui' if html_content else 'non'}")
	if not (pdf_found or png_found or html_content):
		return False

	if html_content and not pdf_found and not png_found:
		print("[DEBUG] Conversion HTML -> PDF via API (style académique)...")
		styled_html = apply_academic_style(
			html_content,
			subject=visible_name,
			sender=email_message.get('From', ''),
			date=format_date_fr(email_message.get('Date', '')),
		)
		if not html_to_pdf(API_KEYS, styled_html, pdf_path):
			print("[DEBUG] Conversion HTML échouée, email ignoré pour ce cycle")
			cleanup_uuid_files(content_uuid)
			return False
		print(f"HTML converted to PDF : {pdf_path}\n")

	metadata = {
		"deleted": False,
		"lastModified": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
		"lastOpened": 0,
		"lastOpenedPage": 0,
		"metadataModified": True,
		"modified": True,
		"parent": "",
		"pinned": False,
		"synced": True,
		"type": "DocumentType",
		"version": 1,
		"visibleName": visible_name
	}
	with open(f"{content_uuid}.metadata", 'w') as f:
		json.dump(metadata, f, indent=2)

	content = {
		"extraMetadata": {},
		"fileType": "pdf",
		"fontName": "Noto Sans",
		"lastOpenedPage": 0,
		"lineHeight": -1,
		"margins": 100,
		"orientation": "portrait",
		"pageCount": 0,
		"textScale": 1,
		"transform": {}
	}
	with open(f"{content_uuid}.content", 'w') as f:
		json.dump(content, f, indent=2)

	files_to_send = glob.glob(f"{content_uuid}*")
	print(f"[DEBUG] Envoi SCP de {files_to_send} vers reMarkable...")
	scp_cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"] \
		+ files_to_send + [f"root@{remarkable_ip}:/home/root/.local/share/remarkable/xochitl/"]
	result = subprocess.run(scp_cmd, capture_output=True, text=True)
	print(f"[DEBUG] Code retour SCP: {result.returncode}")
	if result.returncode != 0:
		print(f"[DEBUG] SCP stderr: {result.stderr}")

	# Nettoyage ciblé : uniquement les fichiers de CE document
	cleanup_uuid_files(content_uuid)

	if result.returncode == 0:
		historique_file.write(message_hash + '\n')
		historique_file.flush()
		list_hash.append(message_hash)
		return 'sent'
	return False


def _clean_title(raw):
	"""Décode les entités HTML basiques et supprime les résidus dans un titre."""
	for entity, char in [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'")]:
		raw = raw.replace(entity, char)
	return re.sub(r'&[a-zA-Z]+;|&#\d+;', '', raw).strip()


# Mots-clés dans class/id qui trahissent un élément de navigation ou chrome de page.
# Volontairement conservateurs : on évite les faux positifs sur du contenu éditorial.
_NAV_KEYWORDS = [
	'menu', 'navbar', 'nav-bar', 'navigation', 'breadcrumb', 'breadcrumbs',
	'sidebar', 'side-bar', 'side_bar',
	'cookie', 'consent', 'gdpr',
	'banner', 'overlay', 'modal', 'popup', 'pop-up',
	'advert', 'advertisement', 'ads-', '-ads', 'pub-',
	'social-share', 'share-bar', 'sharebar',
	'pagination', 'pager',
	'skip-link', 'skipnav',
	'site-header', 'site-footer', 'site-nav',
	'top-bar', 'bottom-bar',
]


def _preprocess_html(raw_html):
	"""Supprime le chrome de page (nav, menus, sidebars…) avant extraction du contenu.

	Stratégie :
	  1. Si <article> ou <main> existe, on extrait uniquement le plus grand
	     (en volume de texte) — ce qui exclut d'emblée toute la navigation.
	  2. Sinon, on supprime agressivement <nav>, <aside>, les éléments dont
	     le class/id contient un mot-clé de navigation, puis on isole <body>.
	"""
	try:
		from lxml import html as lxml_html
		doc = lxml_html.document_fromstring(raw_html)

		# 1. Priorité aux balises sémantiques de contenu
		for tag in ('article', 'main'):
			candidates = doc.xpath(f'//{tag}')
			if candidates:
				best = max(candidates, key=lambda el: len(el.text_content()))
				extracted = lxml_html.tostring(best, encoding='unicode')
				print(f"[DEBUG] _preprocess_html: <{tag}> trouvé ({len(extracted)} chars)")
				return extracted

		# 2. Pas de balise sémantique : nettoyage ciblé
		# Suppression des balises structurelles de navigation
		for tag in ('nav', 'aside', 'footer'):
			for el in doc.xpath(f'//{tag}'):
				parent = el.getparent()
				if parent is not None:
					parent.remove(el)

		# Suppression des éléments dont class ou id contiennent un mot-clé de nav
		for el in doc.xpath('//*[@class or @id]'):
			class_id = (el.get('class', '') + ' ' + el.get('id', '')).lower()
			if any(kw in class_id for kw in _NAV_KEYWORDS):
				parent = el.getparent()
				if parent is not None:
					try:
						parent.remove(el)
					except Exception:
						pass

		# On retourne le <body> nettoyé (ou le document entier si pas de body)
		body = doc.find('.//body')
		root = body if body is not None else doc
		cleaned = lxml_html.tostring(root, encoding='unicode')
		print(f"[DEBUG] _preprocess_html: nettoyage générique, {len(raw_html)} → {len(cleaned)} chars")
		return cleaned

	except Exception as e:
		print(f"[DEBUG] _preprocess_html erreur lxml: {e}")
		return raw_html


def fetch_url_content(url):
	"""Télécharge une URL et extrait le contenu principal (sans menus/header/footer).

	Stratégie en cascade :
	  0. _preprocess_html()  — pré-filtre lxml (article/main, suppression nav)
	  1. trafilatura          — meilleur pour les articles, retourne du HTML structuré
	  2. readability-lxml     — algo Mozilla Readability, bon fallback généraliste
	  3. HTML pré-traité      — dernier recours (déjà nettoyé de la nav)
	"""
	print(f"[DEBUG] fetch_url_content() : {url}")
	headers = {
		'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
		'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
		'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.5',
		'Accept-Encoding': 'gzip, deflate',  # requests ne décompresse pas Brotli
		'DNT': '1',
		'Upgrade-Insecure-Requests': '1',
	}
	try:
		response = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
		response.raise_for_status()
		content_type = response.headers.get('Content-Type', '')
		if 'text/html' not in content_type and 'application/xhtml' not in content_type:
			print(f"[DEBUG] Type de contenu non HTML: {content_type}")
			return None, None
		raw_html = response.text
	except Exception as e:
		print(f"[DEBUG] fetch_url_content() erreur réseau: {e}")
		return None, None

	# Titre extrait du HTML brut (utilisé comme fallback)
	title_match = re.search(r'<title[^>]*>(.*?)</title>', raw_html, re.IGNORECASE | re.DOTALL)
	fallback_title = _clean_title(title_match.group(1)) if title_match else url

	# Pré-traitement : suppression du chrome de page avant les extracteurs
	preprocessed = _preprocess_html(raw_html)

	# --- 1. Tentative trafilatura ---
	try:
		import trafilatura
		meta = trafilatura.extract_metadata(raw_html, default_url=url)
		traf_html = trafilatura.extract(
			preprocessed,
			url=url,
			output_format='html',
			include_formatting=True,
			include_images=True,
			include_links=False,
			favor_recall=True,
		)
		if traf_html:
			title = (meta.title if meta and meta.title else fallback_title)
			print(f"[DEBUG] trafilatura OK, titre: {title[:80]}")
			return f"<div>{traf_html}</div>", title
		print("[DEBUG] trafilatura n'a rien extrait, passage à readability")
	except Exception as e:
		print(f"[DEBUG] trafilatura erreur: {e}")

	# --- 2. Fallback readability-lxml ---
	try:
		from readability import Document
		doc = Document(preprocessed)
		content = doc.summary(html_partial=True)
		title = _clean_title(doc.title())
		if not title or title == '[no-title]':
			title = fallback_title
		if content and len(content) > 200:
			print(f"[DEBUG] readability OK, titre: {title[:80]}")
			return content, title
		print("[DEBUG] readability a retourné trop peu de contenu, passage au HTML pré-traité")
	except Exception as e:
		print(f"[DEBUG] readability erreur: {e}")

	# --- 3. Fallback HTML pré-traité (déjà sans nav) ---
	print("[DEBUG] Utilisation du HTML pré-traité (aucun extracteur n'a fonctionné)")
	return preprocessed, fallback_title


def process_url(url, remarkable_ip):
	"""Télécharge une URL, la convertit en PDF stylisé et l'envoie sur la reMarkable.
	Retourne True si envoyé avec succès, False sinon."""
	content_uuid = uuid.uuid4()
	print(f"[DEBUG] process_url() UUID={content_uuid}, URL={url}")

	html_content, title = fetch_url_content(url)
	if not html_content:
		print(f"[DEBUG] Impossible de récupérer le contenu de {url}")
		return False

	domain_match = re.search(r'https?://([^/]+)', url)
	domain = domain_match.group(1) if domain_match else url

	now = datetime.now()
	date_str = f"{FRENCH_DAYS[now.weekday()]} {now.day} {FRENCH_MONTHS[now.month - 1]} {now.year}"

	styled_html = apply_academic_style(html_content, subject=title, sender=domain, date=date_str)

	pdf_path = f"{content_uuid}.pdf"
	if not html_to_pdf(API_KEYS, styled_html, pdf_path):
		print(f"[DEBUG] Conversion PDF échouée pour {url}")
		cleanup_uuid_files(content_uuid)
		return False

	metadata = {
		"deleted": False,
		"lastModified": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
		"lastOpened": 0,
		"lastOpenedPage": 0,
		"metadataModified": True,
		"modified": True,
		"parent": "",
		"pinned": False,
		"synced": True,
		"type": "DocumentType",
		"version": 1,
		"visibleName": title
	}
	with open(f"{content_uuid}.metadata", 'w') as f:
		json.dump(metadata, f, indent=2)

	content = {
		"extraMetadata": {},
		"fileType": "pdf",
		"fontName": "Noto Sans",
		"lastOpenedPage": 0,
		"lineHeight": -1,
		"margins": 100,
		"orientation": "portrait",
		"pageCount": 0,
		"textScale": 1,
		"transform": {}
	}
	with open(f"{content_uuid}.content", 'w') as f:
		json.dump(content, f, indent=2)

	files_to_send = glob.glob(f"{content_uuid}*")
	print(f"[DEBUG] Envoi SCP de {files_to_send} vers reMarkable...")
	scp_cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"] \
		+ files_to_send + [f"root@{remarkable_ip}:/home/root/.local/share/remarkable/xochitl/"]
	result = subprocess.run(scp_cmd, capture_output=True, text=True)
	print(f"[DEBUG] Code retour SCP: {result.returncode}")
	if result.returncode != 0:
		print(f"[DEBUG] SCP stderr: {result.stderr}")

	cleanup_uuid_files(content_uuid)
	return result.returncode == 0


def main_urls():
	"""Mode URLs : lit URLS_QUEUE.txt, convertit chaque URL en PDF et l'envoie sur la reMarkable.
	Les URLs envoyées avec succès sont retirées du fichier ; les échouées y restent."""
	print("\n" + "=" * 60)
	print(f"[DEBUG] main_urls() démarrée à {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
	print("=" * 60)

	dir_path = os.path.dirname(os.path.abspath(__file__)) + '/'
	queue_path = dir_path + 'URLS_QUEUE.txt'

	if not os.path.exists(queue_path):
		print(f"[DEBUG] Fichier {queue_path} introuvable")
		return

	with open(queue_path, 'r') as f:
		urls = [line.strip() for line in f if line.strip() and line.strip().startswith('http')]

	if not urls:
		print("[DEBUG] Aucune URL à traiter dans URLS_QUEUE.txt")
		return

	print(f"[DEBUG] {len(urls)} URL(s) à traiter")

	remarkable_ip = find_remarkable_ip(REMARKABLE_MAC)
	if not remarkable_ip:
		print("reMarkable not found on network (MAC not in ARP table)")
		return

	if not ping_ip(remarkable_ip):
		print("Remarkable is down")
		return
	print("Remarkable is up")

	sent_urls = []
	failed_urls = []

	for url in urls:
		print(f"\n### Processing URL: {url}")
		try:
			if process_url(url, remarkable_ip):
				sent_urls.append(url)
				print(f"[DEBUG] URL envoyée avec succès: {url}")
			else:
				failed_urls.append(url)
		except Exception as e:
			import traceback
			print(f"Error processing URL {url}: {e}")
			print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")
			failed_urls.append(url)

	# Mise à jour du fichier : on ne conserve que les URLs en échec
	with open(queue_path, 'w') as f:
		for url in failed_urls:
			f.write(url + '\n')

	if sent_urls:
		print(f"\n[DEBUG] {len(sent_urls)} URL(s) envoyée(s), redémarrage xochitl...")
		ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
		           f"root@{remarkable_ip}", "systemctl restart xochitl"]
		result = subprocess.run(ssh_cmd, capture_output=True, text=True)
		print(f"[DEBUG] Code retour SSH: {result.returncode}")

	print(f"\n[DEBUG] Résumé: {len(sent_urls)} envoyée(s), {len(failed_urls)} en échec")


def main():
	print("\n" + "=" * 60)
	print(f"[DEBUG] main() démarrée à {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
	print(f"[DEBUG] HOST={HOST}, PORT={PORT}, USER={USER}")
	print(f"[DEBUG] REMARKABLE_MAC={REMARKABLE_MAC}")
	print(f"[DEBUG] Nombre de clés API: {len(API_KEYS)}")
	print("=" * 60)

	remarkable_ip = find_remarkable_ip(REMARKABLE_MAC)
	if not remarkable_ip:
		print("reMarkable not found on network (MAC not in ARP table)")
		return

	print(f"[DEBUG] IP reMarkable trouvée: {remarkable_ip}")
	if not ping_ip(remarkable_ip):
		print("Remarkable is down")
		return
	print("Remarkable is up")

	mail_server = None
	try:
		print(f"[DEBUG] Connexion POP3 SSL à {HOST}:{PORT}...")
		mail_server = poplib.POP3_SSL(HOST, PORT)
		mail_server.user(USER)
		mail_server.pass_(PASSWORD)
		print("[DEBUG] Authentification POP3 réussie")

		mail_list = mail_server.list()[1]
		num_messages = len(mail_list)
		print(f"[DEBUG] Nombre de messages sur le serveur: {num_messages}")

		dir_path = os.path.dirname(os.path.abspath(__file__)) + '/'
		histo_path = dir_path + 'historique_file.txt'
		list_hash = []
		with open(histo_path, 'r') as f:
			list_hash = [ligne.strip() for ligne in f if ligne.strip()]
		print(f"[DEBUG] {len(list_hash)} hashs chargés depuis l'historique")

		need_reboot = False
		with open(histo_path, 'a') as historique_file:
			for x in range(1, num_messages + 1):
				print(f"\n\n### Processing email n°{x}...")
				try:
					msg = mail_server.retr(x)
					status = process_message(msg, list_hash, historique_file, remarkable_ip)
					if status == 'sent':
						need_reboot = True
					if status in ('sent', 'duplicate'):
						# Marqué pour suppression ; effectif au quit() seulement,
						# donc uniquement si la session se termine proprement
						mail_server.dele(x)
						print(f"[DEBUG] Email n°{x} marqué pour suppression sur le serveur ({status})")
				except Exception as e:
					import traceback
					print(f"Error processing email n°{x}: {e}")
					print(f"[DEBUG] Traceback:\n{traceback.format_exc()}")

		# Le quit() valide les suppressions marquées via dele()
		mail_server.quit()
		mail_server = None
		print("[DEBUG] Connexion POP3 fermée, suppressions validées")

		if need_reboot:
			print("Restart xochitl on remarkable...")
			ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
			           f"root@{remarkable_ip}", "systemctl restart xochitl"]
			result = subprocess.run(ssh_cmd, capture_output=True, text=True)
			print(f"[DEBUG] Code retour SSH: {result.returncode}")
		else:
			print("[DEBUG] need_reboot=False, aucun nouveau document")

	except Exception as e:
		import traceback
		print(f"Error : {e}")
		print(f"[DEBUG] Traceback complet:\n{traceback.format_exc()}")
	finally:
		if mail_server is not None:
			try:
				mail_server.quit()
			except Exception:
				pass


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='email_to_remarkable')
	parser.add_argument('--urls', action='store_true',
	                    help='Traiter les URLs depuis URLS_QUEUE.txt (one-shot) au lieu de relever les emails')
	args = parser.parse_args()

	print("=" * 60)
	print("[DEBUG] Script email_to_remarkable démarré")
	print(f"[DEBUG] PID: {os.getpid()}")
	print(f"[DEBUG] Python: {platform.python_version()}, OS: {platform.system()} {platform.release()}")
	print("=" * 60)

	if args.urls:
		main_urls()
	else:
		print(f"[DEBUG] Intervalle entre relèves: {CHECK_INTERVAL}s")
		loop_count = 0
		while True:
			loop_count += 1
			print(f"\n{'=' * 60}")
			print(f"[DEBUG] Boucle #{loop_count} à {datetime.now().strftime('%H:%M:%S')}")
			print('=' * 60)
			main()
			print(f'\n\nBreak {CHECK_INTERVAL} seconds')
			time.sleep(CHECK_INTERVAL)
