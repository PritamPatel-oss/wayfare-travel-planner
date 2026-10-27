import { supabase } from './supabase';

const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

async function call(path, { method = 'GET', body } = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error('Cannot reach the server. Check your connection and try again.');
  }
  if (!res.ok) {
    let msg = 'Something went wrong. Please try again.';
    try {
      const j = await res.json();
      msg = typeof j.detail === 'string' ? j.detail : 'Please check your inputs and try again.';
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  generate: (prefs) => call('/api/generate', { method: 'POST', body: prefs }),
  regenDay: (b) => call('/api/regenerate-day', { method: 'POST', body: b }),
  listTrips: () => call('/api/trips'),
  createTrip: (b) => call('/api/trips', { method: 'POST', body: b }),
  updateTrip: (id, itinerary) => call(`/api/trips/${id}`, { method: 'PUT', body: { itinerary } }),
  deleteTrip: (id) => call(`/api/trips/${id}`, { method: 'DELETE' }),
};
