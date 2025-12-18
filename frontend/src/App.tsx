import { useState, useEffect } from 'react';
import {
  getSpotifyAuthUrl,
  exchangeCodeForToken,
  runLatentSearch,
  Recommendation,
  ContextSummary,
  SearchSettings,
  DEFAULT_SETTINGS,
  likeArtist,
  unlikeArtist,
  searchExternalSources,
  ExternalTrack,
  shadowSearchWithSpotify,
  ShadowTrack,
  ALL_SOURCES
} from './api';
import './App.css';

type AppState = 'disconnected' | 'connected' | 'searching' | 'results' | 'error';
type SearchMode = 'spotify' | 'external' | 'shadow';

// Generate a simple user ID (persisted in localStorage)
function getUserId(): string {
  let userId = localStorage.getItem('latent_user_id');
  if (!userId) {
    userId = 'user_' + Math.random().toString(36).substring(2, 15);
    localStorage.setItem('latent_user_id', userId);
  }
  return userId;
}

function App() {
  const [state, setState] = useState<AppState>('disconnected');
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [contextSummary, setContextSummary] = useState<ContextSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState<SearchSettings>(DEFAULT_SETTINGS);
  const [likedArtists, setLikedArtists] = useState<Set<string>>(new Set());
  const [searchMode, setSearchMode] = useState<SearchMode>('spotify');
  const [externalQuery, setExternalQuery] = useState('');
  const [externalTracks, setExternalTracks] = useState<ExternalTrack[]>([]);
  const [selectedSources, setSelectedSources] = useState(['audius', 'audiomack', 'archive', 'bandcamp', 'reddit', 'soundcloud']);
  const [shadowTracks, setShadowTracks] = useState<ShadowTrack[]>([]);
  const [shadowGenres, setShadowGenres] = useState<string[]>([]);
  const [deepSearch, setDeepSearch] = useState(false);
  const [expandedPlayer, setExpandedPlayer] = useState<string | null>(null);
  const userId = getUserId();

  const togglePlayer = (trackId: string) => {
    setExpandedPlayer(prev => prev === trackId ? null : trackId);
  };

  // Check for OAuth callback on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');

    if (code) {
      // Clear URL params
      window.history.replaceState({}, '', '/');

      // Exchange code for token
      exchangeCodeForToken(code)
        .then((data) => {
          setAccessToken(data.access_token);
          setState('connected');
          // Store in session for page refreshes
          sessionStorage.setItem('spotify_token', data.access_token);
        })
        .catch((err) => {
          setError(err.message);
          setState('error');
        });
    } else {
      // Check for existing token
      const storedToken = sessionStorage.getItem('spotify_token');
      if (storedToken) {
        setAccessToken(storedToken);
        setState('connected');
      }
    }
  }, []);

  const handleConnectSpotify = async () => {
    try {
      const authUrl = await getSpotifyAuthUrl();
      window.location.href = authUrl;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect');
      setState('error');
    }
  };

  const handleRunSearch = async () => {
    if (!accessToken) return;

    setState('searching');
    setError(null);

    try {
      const response = await runLatentSearch(accessToken, settings);
      setRecommendations(response.recommendations);
      setContextSummary(response.context_summary);
      setState('results');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setState('error');
    }
  };

  const handleDisconnect = () => {
    sessionStorage.removeItem('spotify_token');
    setAccessToken(null);
    setRecommendations([]);
    setContextSummary(null);
    setState('disconnected');
  };

  const toggleExpanded = (artistId: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(artistId)) {
        next.delete(artistId);
      } else {
        next.add(artistId);
      }
      return next;
    });
  };

  const handleExternalSearch = async () => {
    if (!externalQuery.trim()) return;

    setState('searching');
    setError(null);

    try {
      const response = await searchExternalSources(externalQuery, selectedSources, 30);
      setExternalTracks(response.tracks);
      setState('results');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'External search failed');
      setState('error');
    }
  };

  const handleShadowSearch = async () => {
    if (!accessToken) return;

    setState('searching');
    setError(null);

    try {
      const response = await shadowSearchWithSpotify(
        accessToken,
        selectedSources,
        50,
        deepSearch
      );
      setShadowTracks(response.tracks);
      setShadowGenres(response.genres_searched);
      setState('results');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Shadow search failed');
      setState('error');
    }
  };

  const toggleSource = (source: string) => {
    setSelectedSources(prev =>
      prev.includes(source)
        ? prev.filter(s => s !== source)
        : [...prev, source]
    );
  };

  const handleLike = async (rec: Recommendation) => {
    const isLiked = likedArtists.has(rec.artist_id);

    try {
      if (isLiked) {
        await unlikeArtist(userId, rec.artist_id);
        setLikedArtists((prev) => {
          const next = new Set(prev);
          next.delete(rec.artist_id);
          return next;
        });
      } else {
        await likeArtist(userId, rec);
        setLikedArtists((prev) => new Set(prev).add(rec.artist_id));
      }
    } catch (err) {
      console.error('Failed to update like:', err);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Latent Search</h1>
        <p className="tagline">Discover what algorithms exclude</p>
        <div className="mode-toggle">
          <button
            className={`mode-btn ${searchMode === 'spotify' ? 'active' : ''}`}
            onClick={() => setSearchMode('spotify')}
          >
            Spotify Analysis
          </button>
          <button
            className={`mode-btn ${searchMode === 'shadow' ? 'active' : ''}`}
            onClick={() => setSearchMode('shadow')}
          >
            Shadow Search
          </button>
          <button
            className={`mode-btn ${searchMode === 'external' ? 'active' : ''}`}
            onClick={() => setSearchMode('external')}
          >
            External Sources
          </button>
        </div>
      </header>

      <main className="main">
        {/* Shadow Search Mode - Taste-Matched Underground Discovery */}
        {searchMode === 'shadow' && state !== 'searching' && (
          <div className="action-section">
            {!accessToken ? (
              <>
                <p className="description">
                  Shadow Search uses your Spotify listening history to find taste-matched
                  music from underground sources - Audius, Audiomack, Archive.org, and more.
                </p>
                <button className="btn btn-primary" onClick={handleConnectSpotify}>
                  Connect Spotify to Start
                </button>
              </>
            ) : (
              <>
                <p className="description">
                  Find underground music that matches your taste profile across decentralized
                  platforms, African music scenes, and deep archives.
                </p>

                <div className="external-search">
                  <div className="source-toggles source-toggles-grid">
                    {ALL_SOURCES.map(source => (
                      <label key={source.id} className="source-toggle" title={source.description}>
                        <input
                          type="checkbox"
                          checked={selectedSources.includes(source.id)}
                          onChange={() => toggleSource(source.id)}
                        />
                        <span>{source.name}</span>
                      </label>
                    ))}
                  </div>

                  <label className="deep-toggle">
                    <input
                      type="checkbox"
                      checked={deepSearch}
                      onChange={(e) => setDeepSearch(e.target.checked)}
                    />
                    <span>Deep Search (only truly underground sources)</span>
                  </label>

                  <button
                    className="btn btn-primary"
                    onClick={handleShadowSearch}
                    disabled={selectedSources.length === 0}
                  >
                    Run Shadow Search
                  </button>
                </div>

                {shadowTracks.length > 0 && (
                  <div className="external-results">
                    <div className="shadow-summary">
                      <p className="results-count">{shadowTracks.length} shadow tracks found</p>
                      {shadowGenres.length > 0 && (
                        <p className="genres-used">Based on: {shadowGenres.join(', ')}</p>
                      )}
                    </div>
                    <ul className="external-tracks">
                      {shadowTracks.map((track) => (
                        <li key={track.id} className="external-track shadow-track">
                          <div className="track-row">
                            {track.artwork_url && (
                              <img src={track.artwork_url} alt="" className="track-art" />
                            )}
                            <div className="track-info">
                              <a href={track.url} target="_blank" rel="noopener noreferrer" className="track-title">
                                {track.title}
                              </a>
                              <span className="track-artist">{track.artist}</span>
                              <div className="track-meta">
                                <span className={`source-badge ${track.source}`}>{track.source}</span>
                                <span className="shadow-badge" title="Shadow Score">
                                  {(track.shadow_score * 100).toFixed(0)}
                                </span>
                                <span className="taste-badge" title="Taste Match">
                                  {(track.taste_match * 100).toFixed(0)}%
                                </span>
                                {track.genre && <span className="genre-tag">{track.genre}</span>}
                                {track.region && <span className="region-badge">{track.region}</span>}
                              </div>
                            </div>
                            {track.embed_url && (
                              <button
                                className={`play-btn ${expandedPlayer === track.id ? 'active' : ''}`}
                                onClick={() => togglePlayer(track.id)}
                                title={expandedPlayer === track.id ? 'Hide Player' : 'Play'}
                              >
                                {expandedPlayer === track.id ? '⏹' : '▶'}
                              </button>
                            )}
                          </div>
                          {expandedPlayer === track.id && track.embed_url && (
                            <div className="track-player">
                              <iframe
                                src={track.embed_url}
                                title={track.title}
                                allow="autoplay; encrypted-media"
                                loading="lazy"
                              />
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* External Search Mode */}
        {searchMode === 'external' && state !== 'searching' && (
          <div className="action-section">
            <p className="description">
              Search all underground sources directly. Includes Audius (Web3), Audiomack (African),
              Archive.org (netlabels), Bandcamp, Reddit, and SoundCloud.
            </p>

            <div className="external-search">
              <input
                type="text"
                placeholder="Enter genre or artist (e.g., afrobeats, amapiano, experimental)"
                value={externalQuery}
                onChange={(e) => setExternalQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleExternalSearch()}
                className="search-input"
              />

              <div className="source-toggles source-toggles-grid">
                {ALL_SOURCES.map(source => (
                  <label key={source.id} className="source-toggle" title={source.description}>
                    <input
                      type="checkbox"
                      checked={selectedSources.includes(source.id)}
                      onChange={() => toggleSource(source.id)}
                    />
                    <span>{source.name}</span>
                  </label>
                ))}
              </div>

              <button
                className="btn btn-primary"
                onClick={handleExternalSearch}
                disabled={!externalQuery.trim() || selectedSources.length === 0}
              >
                Search Underground
              </button>
            </div>

            {externalTracks.length > 0 && (
              <div className="external-results">
                <p className="results-count">{externalTracks.length} tracks found</p>
                <ul className="external-tracks">
                  {externalTracks.map((track) => (
                    <li key={track.id} className="external-track">
                      <div className="track-row">
                        {track.artwork_url && (
                          <img src={track.artwork_url} alt="" className="track-art" />
                        )}
                        <div className="track-info">
                          <a href={track.url} target="_blank" rel="noopener noreferrer" className="track-title">
                            {track.title}
                          </a>
                          <span className="track-artist">{track.artist}</span>
                          <div className="track-meta">
                            <span className={`source-badge ${track.source}`}>{track.source}</span>
                            <span className="shadow-badge">{(track.shadow_score * 100).toFixed(0)}</span>
                            {track.genre && <span className="genre-tag">{track.genre}</span>}
                          </div>
                        </div>
                        {track.embed_url && (
                          <button
                            className={`play-btn ${expandedPlayer === track.id ? 'active' : ''}`}
                            onClick={() => togglePlayer(track.id)}
                            title={expandedPlayer === track.id ? 'Hide Player' : 'Play'}
                          >
                            {expandedPlayer === track.id ? '⏹' : '▶'}
                          </button>
                        )}
                      </div>
                      {expandedPlayer === track.id && track.embed_url && (
                        <div className="track-player">
                          <iframe
                            src={track.embed_url}
                            title={track.title}
                            allow="autoplay; encrypted-media"
                            loading="lazy"
                          />
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Disconnected State */}
        {state === 'disconnected' && searchMode === 'spotify' && (
          <div className="action-section">
            <p className="description">
              Connect your Spotify account to analyze your listening history
              and surface artists that standard recommendation systems miss.
            </p>
            <button className="btn btn-primary" onClick={handleConnectSpotify}>
              Connect Spotify
            </button>
          </div>
        )}

        {/* Connected State */}
        {state === 'connected' && searchMode === 'spotify' && (
          <div className="action-section">
            <p className="status">Spotify connected</p>

            <button
              className="btn btn-tertiary"
              onClick={() => setShowSettings(!showSettings)}
            >
              {showSettings ? 'Hide Settings' : 'Settings'}
            </button>

            {showSettings && (
              <div className="settings-panel">
                <div className="setting-row">
                  <label>Popularity Range</label>
                  <div className="range-inputs">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={settings.minPopularity}
                      onChange={(e) => setSettings({...settings, minPopularity: parseInt(e.target.value) || 0})}
                    />
                    <span>to</span>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={settings.maxPopularity}
                      onChange={(e) => setSettings({...settings, maxPopularity: parseInt(e.target.value) || 100})}
                    />
                  </div>
                </div>

                <div className="setting-row">
                  <label>Time Range</label>
                  <select
                    value={settings.timeRange}
                    onChange={(e) => setSettings({...settings, timeRange: e.target.value as SearchSettings['timeRange']})}
                  >
                    <option value="all">All Time Periods</option>
                    <option value="short">Recent (~4 weeks)</option>
                    <option value="medium">Medium (~6 months)</option>
                    <option value="long">Long Term (years)</option>
                  </select>
                </div>

                <div className="setting-row">
                  <label>Max Results: {settings.maxResults}</label>
                  <input
                    type="range"
                    min="1"
                    max="20"
                    value={settings.maxResults}
                    onChange={(e) => setSettings({...settings, maxResults: parseInt(e.target.value)})}
                  />
                </div>
              </div>
            )}

            <button className="btn btn-primary" onClick={handleRunSearch}>
              Run Latent Search
            </button>
            <button className="btn btn-secondary" onClick={handleDisconnect}>
              Disconnect
            </button>
          </div>
        )}

        {/* Searching State */}
        {state === 'searching' && (
          <div className="action-section">
            <p className="status">Analyzing listening history...</p>
            <div className="loader"></div>
          </div>
        )}

        {/* Error State */}
        {state === 'error' && (
          <div className="action-section">
            <p className="error">{error}</p>
            <button className="btn btn-secondary" onClick={handleDisconnect}>
              Try Again
            </button>
          </div>
        )}

        {/* Results State */}
        {state === 'results' && searchMode === 'spotify' && (
          <div className="results-section">
            {contextSummary && (
              <div className="context-summary">
                <span>Analyzed {contextSummary.artists_analyzed} artists</span>
                <span className="separator">|</span>
                <span>{contextSummary.recurring_artists} recurring</span>
                <span className="separator">|</span>
                <span>{contextSummary.candidates_evaluated} candidates evaluated</span>
              </div>
            )}

            {recommendations.length === 0 ? (
              <p className="no-results">
                {contextSummary?.message || 'No recommendations found.'}
              </p>
            ) : (
              <ul className="recommendations">
                {recommendations.map((rec, index) => (
                  <li key={rec.artist_id} className="recommendation-item">
                    <div className="rec-main">
                      <span className="rec-number">{index + 1}</span>
                      <div className="rec-content">
                        <div className="rec-header">
                          <span className="rec-artist">{rec.artist_name}</span>
                          <span className="rec-score">
                            {(rec.omission_score * 100).toFixed(0)}
                          </span>
                        </div>
                        {rec.sample_track_name && (
                          <span className="rec-track">{rec.sample_track_name}</span>
                        )}
                        <div className="rec-genres">
                          {rec.genres.map((g) => (
                            <span key={g} className="genre-tag">{g}</span>
                          ))}
                        </div>
                      </div>
                      <button
                        className={`like-btn ${likedArtists.has(rec.artist_id) ? 'liked' : ''}`}
                        onClick={() => handleLike(rec)}
                        title={likedArtists.has(rec.artist_id) ? 'Unlike' : 'Like'}
                      >
                        {likedArtists.has(rec.artist_id) ? '♥' : '♡'}
                      </button>
                      <button
                        className="toggle-btn"
                        onClick={() => toggleExpanded(rec.artist_id)}
                        aria-expanded={expandedItems.has(rec.artist_id)}
                      >
                        {expandedItems.has(rec.artist_id) ? '−' : '+'}
                      </button>
                    </div>

                    {expandedItems.has(rec.artist_id) && (
                      <div className="rec-details">
                        <p className="rec-explanation">{rec.explanation}</p>
                        {rec.found_via_artist && (
                          <p className="rec-source">
                            Found via: {rec.found_via_artist}
                          </p>
                        )}
                        <p className="rec-popularity">
                          Popularity: {rec.popularity}/100
                        </p>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}

            <div className="results-actions">
              <button className="btn btn-secondary" onClick={handleRunSearch}>
                Search Again
              </button>
              <button className="btn btn-secondary" onClick={handleDisconnect}>
                Disconnect
              </button>
            </div>
          </div>
        )}
      </main>

      <footer className="footer">
        <p>Research MVP - Not a consumer product</p>
      </footer>
    </div>
  );
}

export default App;
