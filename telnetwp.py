import socket
import threading
import requests
from html2text import html2text
import textwrap
import re
import os

# ANSI-Escape-Sequenzen für Textformatierung
RESET = "\033[0m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"


def clean_wikipedia_content(content):
    # Entfernen von Fußnoten-Referenzen
    content = re.sub(r'\[\d+\]', '', content)
    
    # Links formatieren
    def format_link(match):
        link_text = match.group(1)
        return f"{CYAN}{link_text}{RESET}"
    
    content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', format_link, content)
    
    # Entfernen von überflüssigen Leerzeichen und Zeilenumbrüchen
    content = re.sub(r'\n\s*\n', '\n\n', content)
    
    return content

def get_wikipedia_content(page_title):
    url = "https://de.wikipedia.org/w/api.php"
    params = {
        "action": "parse",
        "format": "json",
        "page": page_title,
        "prop": "text",
        "formatversion": "2"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            return f"Fehler: {data['error']['info']}"
        
        html_content = data["parse"]["text"]
        text_content = html2text(html_content)
        cleaned_content = clean_wikipedia_content(text_content)
        return cleaned_content
    except requests.RequestException as e:
        return f"Fehler beim Abrufen der Wikipedia-Seite: {str(e)}"

def format_text(text, width=80):
    lines = text.split('\n')
    formatted_lines = []
    for line in lines:
        if line.startswith('# '):  # Hauptüberschrift
            formatted_lines.append(f'\n{BOLD}{RED}{line}{RESET}\n')
        elif line.startswith('## '):  # Unterüberschrift
            formatted_lines.append(f'\n{BOLD}{GREEN}{line}{RESET}\n')
        elif line.startswith('* ') or line.startswith('- '):  # Aufzählungen
            formatted_lines.append(f'{YELLOW}{line}{RESET}')
        elif re.match(r'^\d+\.', line):  # Nummerierte Liste
            formatted_lines.append(f'{BLUE}{line}{RESET}')
        elif line.strip() == '':  # Leerzeilen
            formatted_lines.append(line)
        else:
            # Fettdruck für Wörter in ** **
            line = re.sub(r'\*\*(.*?)\*\*', f'{BOLD}\\1{RESET}', line)
            wrapped = textwrap.fill(line, width=width)
            formatted_lines.append(wrapped)
    return '\n'.join(formatted_lines)

def get_terminal_size():
    try:
        columns, rows = os.get_terminal_size(0)
    except OSError:
        columns, rows = 80, 24
    return columns, rows

def paginate_content(content, page_height):
    lines = content.split('\n')
    pages = []
    current_page = []
    line_count = 0

    for line in lines:
        wrapped_lines = textwrap.wrap(line, width=80)
        if line_count + len(wrapped_lines) > page_height:
            pages.append('\n'.join(current_page))
            current_page = wrapped_lines
            line_count = len(wrapped_lines)
        else:
            current_page.extend(wrapped_lines)
            line_count += len(wrapped_lines)

    if current_page:
        pages.append('\n'.join(current_page))

    return pages

def handle_client(client_socket):
    try:
        client_socket.send(f"{GREEN}Willkommen beim Wikipedia-Telnet-Server!{RESET}\n".encode())
        
        while True:
            client_socket.send(f"\n{YELLOW}Gib einen Seitentitel ein (oder 'quit' zum Beenden): {RESET}".encode())
            data = client_socket.recv(1024).decode().strip()
            if data.lower() == 'quit':
                break
            
            content = get_wikipedia_content(data)
            formatted_content = format_text(content)
            
            _, terminal_height = get_terminal_size()
            pages = paginate_content(formatted_content, terminal_height - 2)
            
            current_page = 0
            while current_page < len(pages):
                client_socket.send(pages[current_page].encode('utf-8', errors='ignore'))
                client_socket.send(f"\n{YELLOW}Seite {current_page + 1}/{len(pages)} - [↓/Space]: Nächste Seite, [↑]: Vorherige Seite, [q]: Zurück zur Suche{RESET}".encode())
                
                nav = client_socket.recv(3)
                if nav == b'\x1b[B' or nav == b' ':  # Pfeil nach unten oder Leertaste
                    current_page = min(current_page + 1, len(pages) - 1)
                elif nav == b'\x1b[A':  # Pfeil nach oben
                    current_page = max(current_page - 1, 0)
                elif nav.lower() == b'q':
                    break
                
                client_socket.send(b"\033[2J\033[H")  # Bildschirm löschen und Cursor nach oben
    
    except Exception as e:
        print(f"Fehler bei der Clientverbindung: {str(e)}")
    finally:
        client_socket.close()

def find_free_port(start_port, max_port=65535):
    for port in range(start_port, max_port + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', port))
            s.close()
            return port
        except OSError:
            pass
    return None

def start_server(host, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((host, port))
    except OSError:
        new_port = find_free_port(port)
        if new_port is None:
            print(f"Konnte keinen freien Port finden. Server wird beendet.")
            return
        print(f"Port {port} ist belegt. Verwende stattdessen Port {new_port}")
        port = new_port
        server.bind((host, port))

    server.listen(5)
    print(f"Server läuft auf {host}:{port}")
    
    try:
        while True:
            client_sock, address = server.accept()
            print(f"Verbindung von {address} akzeptiert")
            client_handler = threading.Thread(target=handle_client, args=(client_sock,))
            client_handler.start()
    except KeyboardInterrupt:
        print("Server wird beendet.")
    except Exception as e:
        print(f"Serverfehler: {str(e)}")
    finally:
        server.close()

if __name__ == "__main__":
    HOST = '127.0.0.1'
    PORT = 8888
    start_server(HOST, PORT)