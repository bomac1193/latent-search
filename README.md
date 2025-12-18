# Latent Search

A research MVP for music discovery that surfaces contextually relevant artists systematically excluded by standard recommendation systems.

## What This Is

Latent Search analyzes your Spotify listening history to find artists you *should* know about but don't. It explicitly penalizes popularity and recency—the exact signals that algorithmic recommendations over-optimize for.

**This is not a consumer product.** It's a testbed for evaluating whether omission-based discovery produces meaningfully different results than engagement-optimized feeds.

## How It Works

### 1. Longitudinal Context Profiling

Instead of treating listening history as a flat preference signal, we build a context profile across three time windows:

- **Short-term** (~4 weeks): Recent listening
- **Medium-term** (~6 months): Stable patterns
- **Long-term** (years): Core identity

Artists appearing in multiple windows are marked as "recurring"—these represent stable context, not momentary interest.

### 2. Candidate Expansion

From your recurring artists, we fetch Spotify's "fans also like" relationships. These are artists contextually adjacent to your listening but potentially absent from your library.

Key filter: **Any artist you've already listened to is excluded.**

### 3. Omission Scoring

Each candidate receives an **omission score** computed from five components:

| Component | Weight | Description |
|-----------|--------|-------------|
| Contextual Similarity | 35% | Genre overlap + audio feature match to your profile |
| Exposure Penalty | 25% | Reward for being absent from your history |
| Playlist Saturation | 15% | Penalty for high-playlist-presence artists |
| Popularity Penalty | 15% | Explicit penalty for popular artists (0-100 scale) |
| Recency Penalty | 10% | Penalty for artists who debuted after 2018 |

**High omission score = "This artist fits your context but you've never encountered them."**

### 4. Output

Returns 5-7 artists maximum. Each result includes:
- Artist name and sample track
- Genres
- Omission score
- Template-based explanation (no AI-generated text)
- Which of your artists led to this discovery

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Spotify Developer Account

### 1. Create Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Set redirect URI to `http://localhost:5173/callback`
4. Note your Client ID and Client Secret

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Spotify credentials

# Run server
uvicorn main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

### 4. Use

1. Open http://localhost:5173
2. Click "Connect Spotify"
3. Authorize the app
4. Click "Run Latent Search"
5. View results

## Project Structure

```
latent-search/
├── backend/
│   ├── main.py              # FastAPI app, endpoints
│   ├── spotify_client.py    # Spotify API wrapper
│   ├── context_builder.py   # Longitudinal profile builder
│   ├── candidate_expander.py # Candidate generation
│   ├── omission_scorer.py   # THE CORE ALGORITHM
│   ├── config.py            # Configuration
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main UI component
│   │   ├── api.ts           # Backend API client
│   │   └── *.css            # Minimal styling
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## Algorithm Details

### Omission Score Formula

```python
omission_score = (
    contextual_similarity * 0.35 +
    exposure_score * 0.25 +
    saturation_score * 0.15 +
    popularity_score * 0.15 +
    recency_score * 0.10
)
```

### Contextual Similarity

Combines:
1. **Genre overlap**: How many of the candidate's genres match your weighted genre profile
2. **Audio feature similarity**: Distance between candidate's track features and your profile center

Audio features compared:
- Energy
- Danceability
- Valence
- Acousticness
- Instrumentalness
- Tempo

### Popularity Penalty

```python
# Popularity is 0-100 (Spotify's scale)
# We cap at 60 to avoid over-penalizing moderate popularity
capped = min(popularity, 60)
popularity_score = 1.0 - (capped / 100)
```

Artists with popularity below 30 get maximum score. Artists above 70 get heavily penalized.

### Recency Penalty

```python
if earliest_album_year <= 2018:
    recency_score = 1.0  # Full score for pre-2018 artists
elif earliest_album_year >= 2023:
    recency_score = 0.2  # Heavy penalty for very recent artists
else:
    # Linear interpolation
    recency_score = interpolate(...)
```

The 2018 cutoff is intentional: it pre-dates the current era of hyper-recency-optimized recommendation.

## Configuration

Key settings in `backend/config.py`:

```python
OMISSION_WEIGHTS = {
    "contextual_similarity": 0.35,
    "exposure_penalty": 0.25,
    "playlist_saturation": 0.15,
    "popularity_penalty": 0.15,
    "recency_penalty": 0.10,
}

POPULARITY_CEILING = 60     # Max popularity before heavy penalty
RECENCY_CUTOFF_YEAR = 2018  # Pre-this = full recency score
MAX_RESULTS = 7             # Never return more than this
```

## Evaluation Criteria

A successful result:
1. Is **relevant** (fits the user's listening context)
2. Is **unfamiliar** (user hasn't heard this artist)
3. Is **explainable** (user can understand why it surfaced)
4. Does **not** feel like a standard Spotify recommendation

If results feel "Spotify-ish," the algorithm needs adjustment.

## What This Doesn't Do

- Generate playlists
- Optimize for engagement
- Add social features
- Use AI text generation
- Return more than 7 results
- Support infinite scroll
- Have a search bar

These are intentional constraints.

## License

Research use only.
