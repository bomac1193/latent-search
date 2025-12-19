"""
SQLite database for storing user feedback.

Two types of feedback:
1. Likes - legacy system for saving artists
2. Feedback - accept/reject verdicts for improving recommendations
"""
import sqlite3
import os
import json
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "latent_search.db")

# Feedback score adjustments
ACCEPT_BOOST = 0.10   # Add to score for accepted artists
REJECT_PENALTY = 0.15  # Subtract from score for rejected artists
HARD_REJECT_COUNT = 2  # Exclude after this many rejections


def init_db():
    """Initialize the database with required tables."""
    with get_connection() as conn:
        # Legacy likes table
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

        # NEW: Feedback table for accept/reject verdicts
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_artist_id TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK(verdict IN ('accept', 'reject')),
                seed_artists TEXT,
                omission_score REAL,
                context_snapshot_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index for fast lookups
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_artist
            ON feedback(candidate_artist_id)
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


# =========================================================================
# FEEDBACK SYSTEM (NEW)
# =========================================================================

def add_feedback(
    candidate_artist_id: str,
    verdict: str,
    seed_artists: list[str] = None,
    omission_score: float = None,
    context_snapshot_id: str = None
) -> bool:
    """
    Record feedback (accept/reject) for a candidate artist.
    Returns True if saved successfully.
    """
    if verdict not in ('accept', 'reject'):
        return False

    with get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO feedback (
                    candidate_artist_id, verdict, seed_artists,
                    omission_score, context_snapshot_id
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                candidate_artist_id,
                verdict,
                json.dumps(seed_artists) if seed_artists else None,
                omission_score,
                context_snapshot_id,
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"[db] Feedback save error: {e}")
            return False


def get_feedback_adjustments() -> dict[str, float]:
    """
    Get score adjustments based on feedback history.

    Returns dict of artist_id -> adjustment value.
    - Positive for accepted artists
    - Negative for rejected artists
    - None (excluded) for artists rejected 2+ times
    """
    adjustments = {}

    with get_connection() as conn:
        # Count accepts and rejects per artist
        cursor = conn.execute("""
            SELECT
                candidate_artist_id,
                SUM(CASE WHEN verdict = 'accept' THEN 1 ELSE 0 END) as accepts,
                SUM(CASE WHEN verdict = 'reject' THEN 1 ELSE 0 END) as rejects
            FROM feedback
            GROUP BY candidate_artist_id
        """)

        for row in cursor.fetchall():
            artist_id = row["candidate_artist_id"]
            accepts = row["accepts"] or 0
            rejects = row["rejects"] or 0

            # Hard exclusion: rejected 2+ times
            if rejects >= HARD_REJECT_COUNT:
                adjustments[artist_id] = -999  # Effectively exclude

            else:
                # Calculate adjustment
                adjustment = (accepts * ACCEPT_BOOST) - (rejects * REJECT_PENALTY)
                if adjustment != 0:
                    adjustments[artist_id] = adjustment

    return adjustments


def get_excluded_artists() -> set[str]:
    """Get artist IDs that should be excluded (rejected 2+ times)."""
    excluded = set()

    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT candidate_artist_id, COUNT(*) as reject_count
            FROM feedback
            WHERE verdict = 'reject'
            GROUP BY candidate_artist_id
            HAVING reject_count >= ?
        """, (HARD_REJECT_COUNT,))

        for row in cursor.fetchall():
            excluded.add(row["candidate_artist_id"])

    return excluded


def get_feedback_history(limit: int = 50) -> list[dict]:
    """Get recent feedback history."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT candidate_artist_id, verdict, seed_artists,
                   omission_score, created_at
            FROM feedback
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_feedback_stats() -> dict:
    """Get aggregate feedback statistics."""
    with get_connection() as conn:
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total_feedback,
                SUM(CASE WHEN verdict = 'accept' THEN 1 ELSE 0 END) as accepts,
                SUM(CASE WHEN verdict = 'reject' THEN 1 ELSE 0 END) as rejects,
                COUNT(DISTINCT candidate_artist_id) as unique_artists
            FROM feedback
        """)
        row = cursor.fetchone()

        return {
            "total_feedback": row["total_feedback"] or 0,
            "accepts": row["accepts"] or 0,
            "rejects": row["rejects"] or 0,
            "unique_artists": row["unique_artists"] or 0,
            "accept_rate": round(
                (row["accepts"] or 0) / max(row["total_feedback"] or 1, 1) * 100, 1
            ),
        }


# =========================================================================
# LEGACY LIKES SYSTEM
# =========================================================================

def add_like(
    user_id: str,
    artist_id: str,
    artist_name: str,
    genres: list[str],
    popularity: int,
    source_genre: Optional[str],
    omission_score: float
) -> bool:
    """Add a like for an artist."""
    with get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO likes (user_id, artist_id, artist_name, genres,
                                   popularity, source_genre, omission_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, artist_id, artist_name, ",".join(genres),
                  popularity, source_genre, omission_score))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def remove_like(user_id: str, artist_id: str) -> bool:
    """Remove a like for an artist."""
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
            SELECT artist_id, artist_name, genres, popularity,
                   source_genre, omission_score, created_at
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
    """Get aggregate stats from user's likes."""
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
            "top_genres": sorted(genre_counts.items(),
                                 key=lambda x: x[1], reverse=True)[:5]
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
            INSERT INTO search_history (user_id, min_popularity, max_popularity,
                                        time_range, max_results, candidates_found)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, min_popularity, max_popularity, time_range,
              max_results, candidates_found))
        conn.commit()


# Initialize database on module load
init_db()
