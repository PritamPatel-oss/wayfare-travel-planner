const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export function getToken() {
  try {
    return localStorage.getItem('wayfare_token');
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem('wayfare_token', token);
    else localStorage.removeItem('wayfare_token');
  } catch { /* ignore */ }
}

export function getUser() {
  try {
    const raw = localStorage.getItem('wayfare_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setUser(user) {
  try {
    if (user) localStorage.setItem('wayfare_user', JSON.stringify(user));
    else localStorage.removeItem('wayfare_user');
  } catch { /* ignore */ }
}

async function call(path, { method = 'GET', body, auth = true } = {}) {
  const token = auth ? getToken() : null;
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error('Cannot reach the server. Check your connection and try again.');
  }
  if (res.status === 401 && auth) {
    setToken(null);
    setUser(null);
    window.dispatchEvent(new Event('wayfare_auth_expired'));
    throw new Error('Your session has expired. Please sign in again.');
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
  signup: (email, password) => call('/api/auth/signup', { method: 'POST', body: { email, password }, auth: false }),
  signin: (email, password) => call('/api/auth/signin', { method: 'POST', body: { email, password }, auth: false }),
  me: () => call('/api/auth/me'),
  generate: (prefs) => call('/api/generate', { method: 'POST', body: prefs }),
  regenDay: (b) => call('/api/regenerate-day', { method: 'POST', body: b }),
  listTrips: () => call('/api/trips'),
  createTrip: (b) => call('/api/trips', { method: 'POST', body: b }),
  updateTrip: (id, itinerary) => call(`/api/trips/${id}`, { method: 'PUT', body: { itinerary } }),
  deleteTrip: (id) => call(`/api/trips/${id}`, { method: 'DELETE' }),
};
