"""
Bandcamp scraper for underground music discovery.

No API key required - uses web scraping.
Bandcamp is excellent for finding indie/underground artists
that don't exist on mainstream platforms.
"""
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional


@dataclass
class BandcampTrack:
    """A track found on Bandcamp."""
    id: str
    title: str
    artist: str
    url: str
    artwork_url: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    embed_url: Optional[str] = None
    source: str = "bandcamp"


def _make_bandcamp_embed_url(track_url: str) -> Optional[str]:
    """Create Bandcamp embed URL from track URL."""
    if not track_url or "bandcamp.com" not in track_url:
        return None
    # Bandcamp embed format - use the track page URL directly
    # The embed will auto-detect from the URL
    return track_url.replace("/track/", "/EmbeddedPlayer/track=") if "/track/" in track_url else None


async def search_bandcamp(
    query: str,
    limit: int = 20
) -> list[BandcampTrack]:
    """
    Search Bandcamp for tracks matching query.

    Args:
        query: Search term (genre, artist, or track name)
        limit: Maximum results to return

    Returns:
        List of BandcampTrack objects
    """
    url = f"https://bandcamp.com/search?q={query}&item_type=t"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LatentSearch/1.0)"}

    tracks: list[BandcampTrack] = []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=5.0)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = soup.find_all("li", class_="searchresult")

        for idx, result in enumerate(results[:limit]):
            heading = result.find("div", class_="heading")
            if not heading:
                continue

            title_elem = heading.find("a")
            artist_elem = result.find("div", class_="subhead")

            title = title_elem.text.strip() if title_elem else "Unknown"
            artist = "Unknown Artist"
            if artist_elem:
                artist = artist_elem.text.strip().replace("by ", "").strip()

            track_url = ""
            if title_elem and "href" in title_elem.attrs:
                track_url = title_elem["href"]

            # Get artwork
            artwork_url = None
            art_elem = result.find("div", class_="art")
            if art_elem:
                img = art_elem.find("img")
                if img and img.get("src"):
                    artwork_url = img["src"]

            # Get album if available
            album = None
            album_elem = result.find("div", class_="itemtype")
            if album_elem and "from" in album_elem.text.lower():
                album_text = album_elem.text.strip()
                if "from " in album_text.lower():
                    album = album_text.split("from ")[-1].strip()

            track = BandcampTrack(
                id=f"bc_{idx}_{hash(title + artist) % 100000}",
                title=title,
                artist=artist,
                url=track_url,
                artwork_url=artwork_url,
                album=album,
                embed_url=_make_bandcamp_embed_url(track_url),
            )
            tracks.append(track)

    except Exception as e:
        print(f"[DEBUG] Bandcamp search failed: {e}")

    return tracks


async def search_bandcamp_by_tag(
    tag: str,
    limit: int = 20
) -> list[BandcampTrack]:
    """
    Search Bandcamp by tag/genre.

    Tags are more reliable than text search for finding
    music in specific genres.
    """
    # Bandcamp tag URL format
    url = f"https://bandcamp.com/tag/{tag.replace(' ', '-')}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LatentSearch/1.0)"}

    tracks: list[BandcampTrack] = []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=5.0)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Tag pages have a different structure
        items = soup.find_all("li", class_="item")

        for idx, item in enumerate(items[:limit]):
            title_elem = item.find("div", class_="itemtext")
            artist_elem = item.find("div", class_="itemsubtext")

            if not title_elem:
                continue

            title = title_elem.text.strip() if title_elem else "Unknown"
            artist = artist_elem.text.strip() if artist_elem else "Unknown Artist"

            # Get link
            link = item.find("a")
            track_url = link["href"] if link and "href" in link.attrs else ""

            # Get artwork
            artwork_url = None
            img = item.find("img")
            if img and img.get("src"):
                artwork_url = img["src"]

            track = BandcampTrack(
                id=f"bc_tag_{idx}_{hash(title + artist) % 100000}",
                title=title,
                artist=artist,
                url=track_url,
                artwork_url=artwork_url,
                embed_url=_make_bandcamp_embed_url(track_url),
            )
            tracks.append(track)

    except Exception as e:
        print(f"[DEBUG] Bandcamp tag search failed: {e}")

    return tracks
