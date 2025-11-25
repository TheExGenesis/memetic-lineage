import { createClient } from '@supabase/supabase-js';

// Top QT tweets database
const topQtUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const topQtKey = process.env.NEXT_PUBLIC_SUPABASE_SECRET;

// Community Archive database
const caUrl = process.env.NEXT_PUBLIC_CA_SUPABASE_URL;
const caKey = process.env.NEXT_PUBLIC_CA_SUPABASE_ANON_KEY;

if (!topQtUrl || !topQtKey) {
  throw new Error('Missing Top QT Supabase environment variables');
}

if (!caUrl || !caKey) {
  throw new Error('Missing Community Archive Supabase environment variables');
}

export const supabaseTopQt = createClient(topQtUrl, topQtKey);
export const supabaseCa = createClient(caUrl, caKey);


