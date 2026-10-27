import { createClient } from '@supabase/supabase-js';

const rawUrl = (import.meta.env.VITE_SUPABASE_URL || 'http://localhost').trim().replace(/\/$/, '');
const rawKey = (import.meta.env.VITE_SUPABASE_ANON_KEY || 'missing-key').trim();

export const isSupabaseConfigured = rawUrl !== 'http://localhost' && rawKey !== 'missing-key';

export const supabase = createClient(rawUrl, rawKey);
