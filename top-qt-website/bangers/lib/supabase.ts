import { createClient } from '@supabase/supabase-js';

// Top QT tweets database
// Try standard Anon key names. 
// NOTE: If you are using the Service Role (Secret) key, DO NOT prefix it with NEXT_PUBLIC_.
const topQtUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const topQtKey = process.env.NEXT_PUBLIC_SUPABASE_KEY;

// Community Archive database
const caUrl = process.env.NEXT_PUBLIC_CA_SUPABASE_URL;
const caKey = process.env.NEXT_PUBLIC_CA_SUPABASE_KEY;

const isBrowser = typeof window !== 'undefined';

if (!topQtUrl || !topQtKey) {
  const msg = 'Missing Top QT Supabase environment variables (URL or ANON KEY). Check .env.local';
  if (isBrowser) console.error(msg);
  else console.warn(msg); // Warn on server to avoid crashing build time if optional
}

if (!caUrl || !caKey) {
  const msg = 'Missing Community Archive Supabase environment variables (URL or ANON KEY). Check .env.local';
  if (isBrowser) console.error(msg);
  else console.warn(msg);
}

// Use non-null assertion or fallback to empty string to prevent crash
export const supabaseTopQt = createClient(topQtUrl || '', topQtKey || '');
export const supabaseCa = createClient(caUrl || '', caKey || '');
