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
