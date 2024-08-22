import socket
import threading
import requests
from PIL import Image
from io import BytesIO
import json
import random
import urllib.parse
import signal
import sys

USER_AGENT = "WikimediaCommonsTelnetViewer/1.0 (https://github.com/yourusername/yourrepository; youremail@example.com)"

server = None

def get_image(query):
    api_url = "https://de.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": query,
        "prop": "images",
        "imlimit": "50"
    }
    headers = {"User-Agent": USER_AGENT}
    
    response = requests.get(api_url, params=params, headers=headers)
    data = response.json()
    
    pages = data['query']['pages']
    page = next(iter(pages.values()))
    
    if 'images' in page:
        image_titles = [img['title'] for img in page['images'] if not img['title'].lower().endswith('.svg')]
        if not image_titles:
            raise Exception("Keine unterstützten Bilder im Artikel gefunden.")
        image_title = random.choice(image_titles)
        
        print(f"Ausgewähltes Bild: {image_title}")  # Debug-Ausgabe
        
        file_params = {
            "action": "query",
            "format": "json",
            "titles": image_title,
            "prop": "imageinfo",
            "iiprop": "url"
        }
        file_response = requests.get(api_url, params=file_params, headers=headers)
        file_data = file_response.json()
        
        file_pages = file_data['query']['pages']
        file_page = next(iter(file_pages.values()))
        image_url = file_page['imageinfo'][0]['url']
    else:
        raise Exception("Keine Bilder im Artikel gefunden.")
    
    print(f"Versuche, Bild von URL zu laden: {image_url}")
    response = requests.get(image_url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Fehler beim Abrufen des Bildes. Status-Code: {response.status_code}")
    
    try:
        return Image.open(BytesIO(response.content)), image_title
    except Exception as e:
        raise Exception(f"Fehler beim Öffnen des Bildes: {str(e)}")


def rgb_to_ansi(r, g, b):
    # Konvertiert RGB zu den nächstgelegenen 8 ANSI-Farben
    ansi_colors = [
        (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
        (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192)
    ]
    distances = [(r-rc)**2 + (g-gc)**2 + (b-bc)**2 for rc, gc, bc in ansi_colors]
    return distances.index(min(distances)) + 30  # ANSI-Farbcodes beginnen bei 30

def convert_to_ascii(image, width=80):
    ascii_chars = ['@', '#', 'S', '%', '?', '*', '+', ';', ':', ',', '.']
    
    image = image.convert("RGB")
    original_width, original_height = image.size
    aspect_ratio = original_height / original_width
    height = int(width * aspect_ratio * 0.55)
    image = image.resize((width, height))
    
    pixels = list(image.getdata())
    ascii_str = ''
    for i, pixel in enumerate(pixels):
        r, g, b = pixel
        ansi_color = rgb_to_ansi(r, g, b)
        char = ascii_chars[sum(pixel) // 3 // 25]
        ascii_str += f"\033[{ansi_color}m{char}\033[0m"
        if (i + 1) % width == 0:
            ascii_str += '\n'
    
    return ascii_str

def handle_client(client_socket):
    client_socket.send(b"Willkommen beim Wikimedia Commons Bildbetrachter!\n")
    while True:
        client_socket.send(b"Geben Sie einen Wikipedia-Artikel oder Bildnamen ein (oder 'exit' zum Beenden): ")
        query = client_socket.recv(1024).decode().strip()
        
        if query.lower() == 'exit':
            break
        
        try:
            image, image_title = get_image(query)
            ascii_image = convert_to_ascii(image)
            client_socket.send(f"Bild: {image_title}\n".encode())
            client_socket.send(ascii_image.encode('utf-8'))
        except Exception as e:
            client_socket.send(f"Fehler: {str(e)}\n".encode())
    
    client_socket.close()

def start_server(port=8888):
    global server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(5)
    print(f"Server läuft auf Port {port}")

    while True:
        try:
            client, addr = server.accept()
            print(f"Verbindung von {addr}")
            client_handler = threading.Thread(target=handle_client, args=(client,))
            client_handler.start()
        except KeyboardInterrupt:
            print("\nServer wird beendet...")
            break

def shutdown_server(signum, frame):
    global server
    print("\nServer wird beendet...")
    if server:
        server.close()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_server)
    signal.signal(signal.SIGTERM, shutdown_server)
    start_server()