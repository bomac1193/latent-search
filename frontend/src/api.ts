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
