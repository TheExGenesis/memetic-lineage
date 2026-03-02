/**
 * Supabase client configuration.
 *
 * NOTE: This file is currently NOT USED. The website now runs on local JSON data.
 * It is kept for potential future real-time integration.
 *
 * To enable Supabase:
 * 1. Set the environment variables below in .env.local
 * 2. Modify lib/api.ts and app/page.tsx to use Supabase clients
 *
 * See CLAUDE.md for full re-integration instructions.
 */

import { createClient } from '@supabase/supabase-js';

// Top QT tweets database (currently unused - data served from local JSON)
const topQtUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const topQtKey = process.env.NEXT_PUBLIC_SUPABASE_KEY;

// Community Archive database (currently unused - data served from local JSON)
const caUrl = process.env.NEXT_PUBLIC_CA_SUPABASE_URL;
const caKey = process.env.NEXT_PUBLIC_CA_SUPABASE_KEY;

// Create clients only if credentials are available
// These are not required for local-first operation
export const supabaseTopQt = topQtUrl && topQtKey
  ? createClient(topQtUrl, topQtKey)
  : null;

export const supabaseCa = caUrl && caKey
  ? createClient(caUrl, caKey)
  : null;

// Helper to check if Supabase is configured
export function isSupabaseConfigured(): boolean {
  return !!(topQtUrl && topQtKey && caUrl && caKey);
}
