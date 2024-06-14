import os
import requests
import logging
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.progress import Progress
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from configparser import ConfigParser
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from fuzzywuzzy import fuzz
import time

log_handler = logging.FileHandler('archiveorg.torrent_downloader.log', encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(log_handler)
logging.getLogger().setLevel(logging.DEBUG)

# Setup Rich console for better output
console = Console()

# Read configuration from a file
config = ConfigParser()
config.read('settings.ini')

# Directory to save .torrent files
download_dir = config.get('settings', 'download_dir', fallback='torrent_files')
os.makedirs(download_dir, exist_ok=True)

# Maximum retries for failed downloads
max_retries = config.getint('settings', 'max_retries', fallback=3)

# Function to download a file from a URL
def download_file(url: str, dest_folder: str, retries: int = max_retries) -> None:
    filename = os.path.join(dest_folder, url.split('/')[-1])
    if os.path.exists(filename):
        logging.info(f"File already exists, skipping download: {filename}")
        console.print(f"[yellow]File already exists, skipping download:[/yellow] {filename}")
        return
    
    for attempt in range(retries):
        try:
            response = requests.get(url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(filename, 'wb') as file:
                    for chunk in response.iter_content(1024):
                        file.write(chunk)
                logging.info(f"Downloaded: {filename}")
                console.print(f"[green]Downloaded:[/green] {filename}")
                return
            else:
                logging.error(f"Failed to download: {url} (status code: {response.status_code})")
                console.print(f"[red]Failed to download:[/red] {url} (status code: {response.status_code})")
        except Exception as e:
            logging.error(f"Error downloading {url}: {e}")
            console.print(f"[red]Error downloading {url}:[/red] {e}")
        logging.info(f"Retrying ({attempt + 1}/{retries})...")
    
    logging.error(f"Failed to download after {retries} attempts: {url}")
    console.print(f"[red]Failed to download after {retries} attempts:[/red] {url}")

# Function to get the list of items from the search endpoint
def search_items(query: str, rows: int = 1000) -> list:
    search_url = f"https://archive.org/advancedsearch.php?q={query}&fl[]=identifier&rows={rows}&output=json"
    logging.info(f"Searching for items with query: {search_url}")
    console.print(f"[cyan]Searching for items...[/cyan]")
    try:
        response = requests.get(search_url, timeout=10)
        response.raise_for_status()
        items = response.json().get('response', {}).get('docs', [])
        logging.info(f"Found {len(items)} items")
        console.print(f"[cyan]Found {len(items)} items[/cyan]")
        return items
    except Exception as e:
        logging.error(f"Failed to search items: {e}")
        console.print(f"[red]Failed to search items: {e}[/red]")
        return []

# Improved function to match multiple terms using fuzzy matching
def match_terms(text: str, keyword: str, threshold: int = 70) -> bool:
    terms = keyword.lower().split()
    for term in terms:
        if fuzz.partial_ratio(term, text.lower()) < threshold:
            return False
    return True

# Function to get the metadata for an item and download the torrent file
def download_torrent(identifier: str, keyword: Optional[str] = None) -> None:
    metadata_url = f"https://archive.org/metadata/{identifier}"
    logging.info(f"Fetching metadata for: {metadata_url}")
    console.print(f"[cyan]Fetching metadata for:[/cyan] {identifier}")
    try:
        response = requests.get(metadata_url, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        if 'files' in metadata:
            torrent_files = [file for file in metadata['files'] if file['name'].endswith('.torrent')]
            if keyword:
                torrent_files = [file for file in torrent_files if match_terms(file['name'], keyword)]
            if not torrent_files:
                logging.warning(f"No matching torrents found for identifier: {identifier} with keyword: {keyword}")
                console.print(f"[yellow]No matching torrents found for identifier:[/yellow] {identifier} with keyword: {keyword}")
            for file in torrent_files:
                torrent_url = f"https://archive.org/download/{identifier}/{file['name']}"
                download_file(torrent_url, download_dir)
        else:
            logging.warning(f"No files found for identifier: {identifier}")
            console.print(f"[yellow]No files found for identifier:[/yellow] {identifier}")
    except Exception as e:
        logging.error(f"Failed to get metadata for: {identifier}: {e}")
        console.print(f"[red]Failed to get metadata for:[/red] {identifier}: {e}")

# Main function to search and download torrents
def main(query: str, num_items: int, keyword: Optional[str] = None) -> None:
    items = search_items(query, num_items)
    with Progress() as progress:
        task = progress.add_task("[cyan]Processing items...", total=len(items))
        with ThreadPoolExecutor(max_workers=5) as executor:
            for item in items:
                identifier = item['identifier']
                executor.submit(download_torrent, identifier, keyword)
                progress.advance(task)

# Display a splash screen
def splash_screen() -> None:
    splash_text = Text("Welcome to the Internet Archive Torrent Downloader", style="bold blue", justify="center")
    layout = Layout()
    layout.split(Layout(name="header", size=3), Layout(name="main", ratio=1), Layout(name="footer", size=3))
    layout["header"].update(Align.center(Text("Initializing...", style="bold magenta")))
    layout["main"].update(Align.center(splash_text))
    layout["footer"].update(Align.center(Text("Loading...", style="bold green")))
    with Live(layout, refresh_per_second=4, screen=True):
        time.sleep(2)

# Display a menu
def display_menu() -> str:
    menu_text = Text()
    menu_text.append("1. Search for torrent files\n", style="bold yellow")
    menu_text.append("2. Exit\n", style="bold yellow")
    panel = Panel.fit(menu_text, title="Main Menu", border_style="bold green")
    console.print(panel)
    choice = Prompt.ask("Enter your choice", choices=["1", "2"])
    return choice

# Main program loop
def run_program() -> None:
    splash_screen()
    while True:
        choice = display_menu()
        if choice == "1":
            # Prompt user for a keyword
            keyword = Prompt.ask("Enter a keyword to filter torrent names (press Enter to download all)").strip()
            if keyword == "":
                keyword = None

            # Prompt user for the number of items to process
            num_items = IntPrompt.ask("Enter the number of items to process", default=100)

            # Define the query
            query = 'format:Torrent'
            if keyword:
                query += f' AND {keyword}'

            # Run the main function
            main(query, num_items, keyword)
        elif choice == "2":
            console.print("[cyan]Exiting the program. Goodbye![/cyan]")
            break

if __name__ == "__main__":
    run_program()
