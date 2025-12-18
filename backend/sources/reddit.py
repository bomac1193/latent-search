"""
Reddit scraper for community-curated music discovery.

No API key required - uses public JSON API.
Scrapes music discovery subreddits where users share
obscure and underground tracks.
"""
import re
import httpx
from dataclasses import dataclass
from typing import Optional


@dataclass
class RedditTrack:
    """A track found on Reddit."""
    id: str
    title: str
    artist: str
    url: str
    subreddit: str
    upvotes: int
    comments: int
    genre: Optional[str] = None
    artwork_url: Optional[str] = None
    embed_url: Optional[str] = None
    source: str = "reddit"


# Music discovery subreddits
MUSIC_SUBREDDITS = [
    "listentothis",      # Obscure music discoveries
    "under10k",          # Artists with <10k listeners
    "futurebeats",       # Electronic/experimental
    "experimentalmusic", # Experimental/avant-garde
    "obscuremusic",      # Obscure finds
    "truemusic",         # Quality over popularity
]


def _parse_reddit_title(title: str) -> dict:
    """
    Parse Reddit music post titles.

    Common formats:
    - "Artist - Song [Genre]"
    - "Artist - Song (Genre)"
    - "Artist -- Song"
    """
    result = {"artist": None, "title": None, "genre": None}

    # Extract genre from brackets
    genre_match = re.search(r'\[([^\]]+)\]', title)
    if genre_match:
        result["genre"] = genre_match.group(1)
        title = re.sub(r'\[[^\]]+\]', '', title).strip()

    # Try parentheses for genre
    if not result["genre"]:
        paren_match = re.search(r'\(([^)]+)\)$', title)
        if paren_match:
            potential_genre = paren_match.group(1)
            # Only treat as genre if it looks like one (short, no numbers)
            if len(potential_genre) < 30 and not re.search(r'\d{4}', potential_genre):
                result["genre"] = potential_genre
                title = re.sub(r'\([^)]+\)$', '', title).strip()

    # Split artist and title
    separators = [' - ', ' -- ', ' – ', ' — ', ' | ']
    for sep in separators:
        if sep in title:
            parts = title.split(sep, 1)
            result["artist"] = parts[0].strip()
            result["title"] = parts[1].strip()
            break

    # Clean up
    if result["title"]:
        result["title"] = re.sub(r'\s+', ' ', result["title"]).strip()
    if result["artist"]:
        result["artist"] = re.sub(r'\s+', ' ', result["artist"]).strip()

    return result


def _extract_embed_url(url: str) -> Optional[str]:
    """Extract embeddable URL from music platform links."""
    if 'youtube.com' in url or 'youtu.be' in url:
        if 'v=' in url:
            video_id = url.split('v=')[1].split('&')[0]
            return f"https://www.youtube.com/embed/{video_id}"
        elif 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[1].split('?')[0]
            return f"https://www.youtube.com/embed/{video_id}"
    elif 'soundcloud.com' in url:
        return f"https://w.soundcloud.com/player/?url={url}&auto_play=false"
    elif 'bandcamp.com' in url:
        return url  # Bandcamp doesn't have simple embeds
    return None


async def search_reddit(
    query: str,
    limit: int = 50,
    subreddits: Optional[list[str]] = None
) -> list[RedditTrack]:
    """
    Search Reddit music subreddits for tracks.

    Args:
        query: Search term
        limit: Maximum results to return
        subreddits: Specific subreddits to search (defaults to MUSIC_SUBREDDITS)

    Returns:
        List of RedditTrack objects
    """
    if subreddits is None:
        subreddits = MUSIC_SUBREDDITS

    tracks: list[RedditTrack] = []
    headers = {"User-Agent": "LatentSearch/1.0"}

    async with httpx.AsyncClient() as client:
        for subreddit in subreddits:
            if len(tracks) >= limit:
                break

            try:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {
                    "q": query,
                    "restrict_sr": "on",
                    "sort": "relevance",
                    "limit": 100,
                    "t": "all"
                }

                response = await client.get(
                    url, params=params, headers=headers, timeout=5.0
                )
                response.raise_for_status()
                data = response.json()

                for post in data.get("data", {}).get("children", []):
                    if len(tracks) >= limit:
                        break

                    post_data = post.get("data", {})
                    title = post_data.get("title", "")

                    # Parse the title
                    parsed = _parse_reddit_title(title)
                    if not parsed["artist"] or not parsed["title"]:
                        continue

                    # Get thumbnail
                    artwork_url = None
                    thumbnail = post_data.get("thumbnail", "")
                    if thumbnail and thumbnail not in ["self", "default", "nsfw", ""]:
                        artwork_url = thumbnail

                    # Get music URL
                    music_url = post_data.get("url", "")
                    reddit_url = f"https://reddit.com{post_data.get('permalink', '')}"

                    # Skip if URL is just the reddit post
                    if "reddit.com" in music_url:
                        music_url = reddit_url

                    # Get embed URL
                    embed_url = _extract_embed_url(music_url)

                    track = RedditTrack(
                        id=f"reddit_{post_data.get('id', '')}",
                        title=parsed["title"],
                        artist=parsed["artist"],
                        url=music_url,
                        subreddit=subreddit,
                        upvotes=post_data.get("ups", 0),
                        comments=post_data.get("num_comments", 0),
                        genre=parsed["genre"],
                        artwork_url=artwork_url,
                        embed_url=embed_url,
                    )
                    tracks.append(track)

            except Exception as e:
                print(f"[DEBUG] Reddit search failed for r/{subreddit}: {e}")
                continue

    return tracks


async def get_reddit_top(
    subreddit: str = "listentothis",
    time_filter: str = "week",
    limit: int = 50
) -> list[RedditTrack]:
    """
    Get top posts from a music subreddit.

    Args:
        subreddit: Subreddit name
        time_filter: "hour", "day", "week", "month", "year", "all"
        limit: Maximum results

    Returns:
        List of RedditTrack objects
    """
    tracks: list[RedditTrack] = []
    headers = {"User-Agent": "LatentSearch/1.0"}

    try:
        async with httpx.AsyncClient() as client:
            url = f"https://www.reddit.com/r/{subreddit}/top.json"
            params = {"t": time_filter, "limit": limit}

            response = await client.get(
                url, params=params, headers=headers, timeout=5.0
            )
            response.raise_for_status()
            data = response.json()

            for post in data.get("data", {}).get("children", []):
                post_data = post.get("data", {})
                title = post_data.get("title", "")

                parsed = _parse_reddit_title(title)
                if not parsed["artist"] or not parsed["title"]:
                    continue

                music_url = post_data.get("url", "")
                embed_url = _extract_embed_url(music_url)

                artwork_url = None
                thumbnail = post_data.get("thumbnail", "")
                if thumbnail and thumbnail not in ["self", "default", "nsfw", ""]:
                    artwork_url = thumbnail

                track = RedditTrack(
                    id=f"reddit_{post_data.get('id', '')}",
                    title=parsed["title"],
                    artist=parsed["artist"],
                    url=music_url,
                    subreddit=subreddit,
                    upvotes=post_data.get("ups", 0),
                    comments=post_data.get("num_comments", 0),
                    genre=parsed["genre"],
                    artwork_url=artwork_url,
                    embed_url=embed_url,
                )
                tracks.append(track)

    except Exception as e:
        print(f"[DEBUG] Reddit top failed for r/{subreddit}: {e}")

    return tracks
