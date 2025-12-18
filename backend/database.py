"""
SQLite database for storing user feedback (likes).

Used to learn what "latent" means to users over time.
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "latent_search.db")


def init_db():
    """Initialize the database with required tables."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                artist_id TEXT NOT NULL,
                artist_name TEXT,
                genres TEXT,
                popularity INTEGER,
                source_genre TEXT,
                omission_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, artist_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                min_popularity INTEGER,
                max_popularity INTEGER,
                time_range TEXT,
                max_results INTEGER,
                candidates_found INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()


@contextmanager
def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def add_like(
    user_id: str,
    artist_id: str,
    artist_name: str,
    genres: list[str],
    popularity: int,
    source_genre: Optional[str],
    omission_score: float
) -> bool:
    """
    Add a like for an artist.
    Returns True if added, False if already exists.
    """
    with get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO likes (user_id, artist_id, artist_name, genres, popularity, source_genre, omission_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, artist_id, artist_name, ",".join(genres), popularity, source_genre, omission_score))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def remove_like(user_id: str, artist_id: str) -> bool:
    """
    Remove a like for an artist.
    Returns True if removed, False if didn't exist.
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            DELETE FROM likes WHERE user_id = ? AND artist_id = ?
        """, (user_id, artist_id))
        conn.commit()
        return cursor.rowcount > 0


def get_user_likes(user_id: str) -> list[dict]:
    """Get all likes for a user."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT artist_id, artist_name, genres, popularity, source_genre, omission_score, created_at
            FROM likes WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def is_liked(user_id: str, artist_id: str) -> bool:
    """Check if a user has liked an artist."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT 1 FROM likes WHERE user_id = ? AND artist_id = ?
        """, (user_id, artist_id))
        return cursor.fetchone() is not None


def get_like_stats(user_id: str) -> dict:
    """
    Get aggregate stats from user's likes.
    Used for learning preferences.
    """
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total_likes,
                AVG(popularity) as avg_popularity,
                MIN(popularity) as min_popularity,
                MAX(popularity) as max_popularity,
                AVG(omission_score) as avg_omission_score
            FROM likes WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()

        # Get genre counts
        cursor = conn.execute("""
            SELECT genres FROM likes WHERE user_id = ?
        """, (user_id,))

        genre_counts: dict[str, int] = {}
        for row_genres in cursor.fetchall():
            if row_genres["genres"]:
                for genre in row_genres["genres"].split(","):
                    genre = genre.strip()
                    if genre:
                        genre_counts[genre] = genre_counts.get(genre, 0) + 1

        return {
            "total_likes": row["total_likes"] or 0,
            "avg_popularity": round(row["avg_popularity"] or 0, 1),
            "min_popularity": row["min_popularity"] or 0,
            "max_popularity": row["max_popularity"] or 0,
            "avg_omission_score": round(row["avg_omission_score"] or 0, 3),
            "top_genres": sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        }


def log_search(
    user_id: str,
    min_popularity: int,
    max_popularity: int,
    time_range: str,
    max_results: int,
    candidates_found: int
):
    """Log a search for analytics."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO search_history (user_id, min_popularity, max_popularity, time_range, max_results, candidates_found)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, min_popularity, max_popularity, time_range, max_results, candidates_found))
        conn.commit()


# Initialize database on module load
init_db()
