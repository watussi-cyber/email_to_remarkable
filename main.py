import subprocess
from email.header import decode_header
import platform
import base64
import time
from email.parser import Parser
import poplib
from PIL import Image 
from datetime import datetime, UTC
import json
import requests
import os
import hashlib
import uuid
import configparser
import random

config = configparser.ConfigParser()
config.read("config.cfg")

REMARKABLE_IP = config.get('PROD', 'REMARKABLE_IP')

HOST = config.get('PROD', 'HOST')  
PORT = 995
USER = config.get('PROD', 'USER') 
PASSWORD = config.get('PROD', 'PASSWORD')

API_KEYS = config.get('PROD', 'API_KEYS').split(";")


def png_to_pdf(png_path, pdf_path):
    try:
        with Image.open(png_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(pdf_path, "PDF")
        print(f"PNG converti en PDF avec succès : {pdf_path}")
    except Exception as e:
        print(f"Erreur lors de la conversion PNG en PDF : {e}")


def decode_mime_subject(encoded_subject):
	decoded_parts = decode_header(encoded_subject)
	subject = ""
	for part, encoding in decoded_parts:
		if isinstance(part, bytes):
			subject += part.decode(encoding or 'utf-8', errors='ignore')
		else:
			subject += part

	return subject

def ping_ip(ip_address, timeout=5):
	os_type = platform.system().lower()
	if os_type == "darwin":  # MacOS
		command = ["ping", "-c", "1", "-W", str(timeout * 1000), ip_address]
	elif os_type == "linux":
		command = ["ping", "-c", "1", "-W", str(timeout), ip_address]
	else:
		raise OSError("OS not supported. Use MacOS or Linux.")
	
	try:
		result = subprocess.run(
			command,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			timeout=timeout
		)
		return result.returncode == 0
		
	except subprocess.TimeoutExpired:
		return False
	except subprocess.SubprocessError:
		return False
	except Exception as e:
		print(f"Ping error: {str(e)}")
		return False


def html_to_pdf(api_key, html_content, output_pdf):
	api_url = "https://api.html2pdfrocket.com/pdf"
	data = {
		"apikey": api_key,
		"value": html_content
	}

	try:
		response = requests.post(api_url, data=data)
		if response.status_code == 200:
			with open(output_pdf, 'wb') as pdf_file:
				pdf_file.write(response.content)
			print(f"PDF conversion successful : {output_pdf}")
		else:
			print(f"Error during PDF conversion: {response.status_code} - {response.text}")

	except Exception as e:
		print(f"Error : {e}")


def main():
	remarkable_up = ping_ip(REMARKABLE_IP)
	
	if not remarkable_up:
		print("Remarkable is down")
	else:
		print("Remarkable is up")
		try:
			mail_server = poplib.POP3_SSL(HOST, PORT)
			mail_server.user(USER)
			mail_server.pass_(PASSWORD)

			messages = [mail_server.retr(i) for i in range(1, len(mail_server.list()[1]) + 1)]

			need_reboot = False

			dir_path = os.path.dirname(os.path.abspath(__file__)) + '/'
			list_hash = list()
			with open(dir_path + 'historique_file.txt', 'r') as f:
				for ligne in f:
					ligne = ligne.strip()
					list_hash.append(ligne)
			
			with open(dir_path + 'historique_file.txt', 'a') as historique_file:
				x = 1
				for msg in messages:
					print(f"\n\n### Processing email n°{x}...")
					x = x + 1
					content_uuid = uuid.uuid4()
					print("Reading email...")
					msg_content = b'\r\n'.join(msg[1])
					message_hash = hashlib.sha256(msg_content).hexdigest()

					email_message = Parser().parsestr(msg_content.decode('utf-8', errors='ignore'))
					visible_name = decode_mime_subject(email_message['subject'])
					print(f"Email subject : {visible_name}")

					if message_hash in list_hash:
						print(f"Email already processed : {message_hash}")
						continue
					print(f"Hash : {message_hash}")

					pdf_found = False
					png_found = False
					html_content = None

					if email_message.is_multipart():
						for part in email_message.walk():

							if part.get_content_type() == 'image/png' and part.get('Content-Disposition') is not None:
							            filename = part.get_filename()
							            if filename and filename.lower().endswith('.png'):
							                print('PNG found')
							                png_found = True
							                payload = part.get_payload(decode=False)
							                if 'base64' in part.get('Content-Transfer-Encoding', '').lower():
							                    attachment = base64.b64decode(payload)
							                else:
							                    attachment = part.get_payload(decode=True)
							                
							                png_path = f"{content_uuid}.png"
							                with open(png_path, 'wb') as f:
							                    f.write(attachment)
							                print(f"PNG donwloaded : {png_path}")
							                
							                pdf_path = f"{content_uuid}.pdf"
							                png_to_pdf(png_path, pdf_path)
							                print(f"PDF created from PNG : {pdf_path}")
							                os.system(f"rm *.png")
							                visible_name = filename

							if part.get_content_maintype() == 'application' and part.get('Content-Disposition') is not None:
								filename = part.get_filename()
								if filename and filename.lower().endswith('.pdf'):
									pdf_found = True
									print('PDF found')
									payload = part.get_payload(decode=False)
									if 'base64' in part.get('Content-Transfer-Encoding', '').lower():
										attachment = base64.b64decode(payload)
									else:
										attachment = part.get_payload(decode=True)
									
									visible_name = filename
									counter = 1

									with open(f'{content_uuid}.pdf', 'wb') as f:
										f.write(attachment)
									print(f"PDF download successful")

							elif not pdf_found and part.get_content_type() == "text/html":
								html_content = part.get_payload(decode=True)
								charset = part.get_content_charset()
								if html_content:
									print('HTML content found')
									html_content = html_content.decode(charset or 'utf-8', errors='ignore')

					else:
						if email_message.get_content_type() == "text/html":
							html_content = email_message.get_payload(decode=True)
							charset = email_message.get_content_charset()
							if html_content:
								print('HTML content found')
								html_content = html_content.decode(charset or 'utf-8', errors='ignore')

					if pdf_found or png_found or html_content:
						if html_content and not pdf_found and not png_found:
							pdf_file = f"{content_uuid}.pdf"
							random.shuffle(API_KEYS)
							api_key = API_KEYS[0]
							html_to_pdf(api_key, html_content, pdf_file)
							print(f"HTML converted to PDF : {pdf_file}\n")

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

						tmp = os.system(f"scp {content_uuid}* root@{REMARKABLE_IP}:/home/root/.local/share/remarkable/xochitl/")
						print(tmp)

						if tmp == 0:
							historique_file.write(message_hash + '\n')
							need_reboot = True

			if need_reboot:
				print("Reboot remarkable...")
				os.system(f"rm *.pdf *.content *.metadata")
				os.system(f"ssh root@{REMARKABLE_IP} \"systemctl restart xochitl\"")

			print('\n\nBreak 10 minutes')
			time.sleep(600)

			mail_server.quit()
		except Exception as e:
			print(f"Error : {e}")



if __name__ == "__main__":
	while True:
		heure_actuelle = datetime.now().strftime("%H:%M:%S")
		print(heure_actuelle)
		main()
		print('\n\nBreak one minute')
		time.sleep(60)
