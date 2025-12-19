/**
 * API client for Latent Search backend.
 */

const API_BASE = '/api';

export interface Recommendation {
  artist_id: string;
  artist_name: string;
  sample_track_name: string | null;
  genres: string[];
  popularity: number;
  omission_score: number;
  explanation: string;
  found_via_artist: string | null;
}

export interface ContextSummary {
  artists_analyzed: number;
  recurring_artists: number;
  genres_found: number;
  top_genres?: string[];
  candidates_evaluated?: number;
  message?: string;
}

export interface SearchResponse {
  recommendations: Recommendation[];
  context_summary: ContextSummary;
}

/**
 * Get Spotify OAuth authorization URL.
 */
export async function getSpotifyAuthUrl(): Promise<string> {
  const response = await fetch(`${API_BASE}/auth/spotify/url`);
  if (!response.ok) {
    throw new Error('Failed to get auth URL');
  }
  const data = await response.json();
  return data.auth_url;
}

/**
 * Exchange OAuth code for access token.
 */
export async function exchangeCodeForToken(code: string): Promise<{
  access_token: string;
  refresh_token: string;
  expires_in: number;
}> {
  const response = await fetch(`${API_BASE}/auth/spotify/callback?code=${encodeURIComponent(code)}`);
  if (!response.ok) {
    throw new Error('Failed to exchange code for token');
  }
  return response.json();
}

export interface SearchSettings {
  minPopularity: number;
  maxPopularity: number;
  timeRange: 'short' | 'medium' | 'long' | 'all';
  maxResults: number;
}

export const DEFAULT_SETTINGS: SearchSettings = {
  minPopularity: 5,
  maxPopularity: 60,
  timeRange: 'all',
  maxResults: 7,
};

/**
 * Run Latent Search algorithm.
 */
export async function runLatentSearch(
  accessToken: string,
  settings: SearchSettings = DEFAULT_SETTINGS
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    access_token: accessToken,
    min_popularity: settings.minPopularity.toString(),
    max_popularity: settings.maxPopularity.toString(),
    time_range: settings.timeRange,
    max_results: settings.maxResults.toString(),
  });

  const response = await fetch(`${API_BASE}/search?${params}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Search failed' }));
    throw new Error(error.detail || 'Search failed');
  }
  return response.json();
}

/**
 * Like an artist recommendation.
 */
export async function likeArtist(
  userId: string,
  artist: Recommendation
): Promise<{ success: boolean; liked: boolean }> {
  const response = await fetch(`${API_BASE}/like`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      artist_id: artist.artist_id,
      artist_name: artist.artist_name,
      genres: artist.genres,
      popularity: artist.popularity,
      source_genre: artist.found_via_artist,
      omission_score: artist.omission_score,
    }),
  });
  return response.json();
}

/**
 * Unlike an artist.
 */
export async function unlikeArtist(
  userId: string,
  artistId: string
): Promise<{ success: boolean; liked: boolean }> {
  const response = await fetch(
    `${API_BASE}/like?user_id=${encodeURIComponent(userId)}&artist_id=${encodeURIComponent(artistId)}`,
    { method: 'DELETE' }
  );
  return response.json();
}

/**
 * Get all liked artists for a user.
 */
export async function getLikes(userId: string): Promise<{ likes: any[] }> {
  const response = await fetch(`${API_BASE}/likes?user_id=${encodeURIComponent(userId)}`);
  return response.json();
}

/**
 * Check if an artist is liked.
 */
export async function checkLike(userId: string, artistId: string): Promise<{ liked: boolean }> {
  const response = await fetch(
    `${API_BASE}/likes/check?user_id=${encodeURIComponent(userId)}&artist_id=${encodeURIComponent(artistId)}`
  );
  return response.json();
}

export interface LikeStats {
  total_likes: number;
  avg_popularity: number;
  min_popularity: number;
  max_popularity: number;
  avg_omission_score: number;
  top_genres: [string, number][];
}

/**
 * Get like statistics for a user.
 */
export async function getLikeStats(userId: string): Promise<LikeStats> {
  const response = await fetch(`${API_BASE}/likes/stats?user_id=${encodeURIComponent(userId)}`);
  return response.json();
}

// =========================================================================
// EXTERNAL SOURCE SEARCH
// =========================================================================

export interface ExternalTrack {
  id: string;
  title: string;
  artist: string;
  source: string;
  url: string;
  artwork_url: string | null;
  embed_url: string | null;
  genre: string | null;
  plays: number | null;
  upvotes: number | null;
  shadow_score: number;
}

export interface ExternalSearchResponse {
  tracks: ExternalTrack[];
  sources_searched: string[];
  total_found: number;
}

/**
 * Search external sources for underground music.
 */
export async function searchExternalSources(
  query: string,
  sources: string[] = ['bandcamp', 'reddit', 'soundcloud', 'audius', 'audiomack', 'archive'],
  limit: number = 30
): Promise<ExternalSearchResponse> {
  const params = new URLSearchParams({
    query,
    sources: sources.join(','),
    limit: limit.toString(),
  });

  const response = await fetch(`${API_BASE}/search/external?${params}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'External search failed' }));
    throw new Error(error.detail || 'External search failed');
  }
  return response.json();
}

// =========================================================================
// SHADOW SEARCH - TASTE-MATCHED UNDERGROUND DISCOVERY
// =========================================================================

export interface ShadowTrack {
  id: string;
  title: string;
  artist: string;
  source: string;
  url: string;
  artwork_url: string | null;
  genre: string | null;
  plays: number | null;
  shadow_score: number;
  taste_match: number;
  combined_score: number;
  region: string | null;
  embed_url: string | null;
}

export interface ShadowSearchResponse {
  tracks: ShadowTrack[];
  genres_searched: string[];
  sources_searched: string[];
  total_found: number;
}

/**
 * Shadow search with explicit genres.
 * Finds taste-matched underground music across all sources.
 */
export async function shadowSearch(
  genres: string[],
  sources: string[] = ['audius', 'audiomack', 'archive', 'bandcamp', 'reddit', 'soundcloud'],
  limit: number = 30,
  deep: boolean = false
): Promise<ShadowSearchResponse> {
  const params = new URLSearchParams({
    genres: genres.join(','),
    sources: sources.join(','),
    limit: limit.toString(),
    deep: deep.toString(),
  });

  const response = await fetch(`${API_BASE}/search/shadow?${params}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Shadow search failed' }));
    throw new Error(error.detail || 'Shadow search failed');
  }
  return response.json();
}

/**
 * Shadow search using Spotify profile.
 * Automatically extracts genres from Spotify listening history.
 */
export async function shadowSearchWithSpotify(
  accessToken: string,
  sources: string[] = ['audius', 'audiomack', 'archive', 'bandcamp', 'reddit', 'soundcloud'],
  limit: number = 30,
  deep: boolean = false
): Promise<ShadowSearchResponse> {
  const params = new URLSearchParams({
    access_token: accessToken,
    sources: sources.join(','),
    limit: limit.toString(),
    deep: deep.toString(),
  });

  const response = await fetch(`${API_BASE}/search/shadow/spotify?${params}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Shadow search failed' }));
    throw new Error(error.detail || 'Shadow search failed');
  }
  return response.json();
}

// All available external sources
export const ALL_SOURCES = [
  // Original sources
  { id: 'audius', name: 'Audius', description: 'Decentralized Web3 music' },
  { id: 'audiomack', name: 'Audiomack', description: 'African & underground hip-hop' },
  { id: 'archive', name: 'Archive.org', description: 'Netlabels & live recordings' },
  { id: 'bandcamp', name: 'Bandcamp', description: 'Indie & underground' },
  { id: 'reddit', name: 'Reddit', description: 'Community curated' },
  { id: 'soundcloud', name: 'SoundCloud', description: 'Emerging artists' },
  // NEW: Global underground sources
  { id: 'vk', name: 'VK Music', description: 'Russian underground (390M users)' },
  { id: 'telegram', name: 'Telegram', description: 'Music channels & leaks' },
  { id: 'netease', name: 'NetEase', description: 'Chinese indie (611K artists)' },
  { id: 'funkwhale', name: 'Funkwhale', description: 'Federated self-hosted music' },
  { id: 'mixcloud', name: 'Mixcloud', description: 'DJ mixes & radio shows' },
];
