import { useEffect, useState } from 'react';
import { supabase } from './supabase';
import { api } from './api';
import Planner from './Planner.jsx';
import Itinerary from './Itinerary.jsx';

function Auth() {
  const [mode, setMode] = useState('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setMsg('');
    const fn = mode === 'signin' ? supabase.auth.signInWithPassword : supabase.auth.signUp;
    const { data, error } = await fn.call(supabase.auth, { email, password });
    setBusy(false);
    if (error) setMsg(error.message);
    else if (mode === 'signup' && !data.session) setMsg('Account created. Check your email to confirm, then sign in.');
  }

  return (
    <main className="auth">
      <section className="auth-pitch">
        <div className="brand">Wayfare</div>
        <h1>Tell us where.<br />We plan the days.</h1>
        <p>Pick a destination, a budget and what you enjoy. Get a day-by-day plan with food, sights and costs you can edit and keep.</p>
      </section>
      <form className="auth-card" onSubmit={submit}>
        <h2>{mode === 'signin' ? 'Sign in' : 'Create your account'}</h2>
        <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
        <label>Password<input type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === 'signin' ? 'current-password' : 'new-password'} /></label>
        {msg && <p className="notice" role="alert">{msg}</p>}
        <button className="btn primary" disabled={busy}>{busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : 'Create account'}</button>
        <button type="button" className="link" onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setMsg(''); }}>
          {mode === 'signin' ? 'New here? Create an account' : 'Already have an account? Sign in'}
        </button>
      </form>
    </main>
  );
}

function TripList({ trips, loading, onOpen, onDelete, onNew }) {
  if (loading) return <p className="muted">Loading your trips…</p>;
  if (!trips.length)
    return (
      <div className="empty">
        <h2>No trips yet</h2>
        <p>Plan your first trip and it will be saved here.</p>
        <button className="btn primary" onClick={onNew}>Plan a trip</button>
      </div>
    );
  return (
    <div className="trip-grid">
      {trips.map((t) => (
        <article key={t.id} className="trip-card">
          <button className="trip-open" onClick={() => onOpen(t)}>
            <div className="trip-img" style={t.itinerary?.cover?.url ? { backgroundImage: `url(${t.itinerary.cover.url})` } : undefined} />
            <h3>{t.itinerary?.title || t.destination}</h3>
            <p className="muted">{t.destination}, {t.days} {t.days === 1 ? 'day' : 'days'}</p>
          </button>
          <button className="link danger" onClick={() => onDelete(t)}>Delete</button>
        </article>
      ))}
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState(undefined);
  const [view, setView] = useState('home'); // home | plan | trip
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(false);
  const [trip, setTrip] = useState(null);
  const [toast, setToast] = useState('');

  useEffect(() => {
    supabase.auth
      .getSession()
      .then(({ data }) => setSession(data?.session || null))
      .catch(() => setSession(null));
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data?.subscription?.unsubscribe();
  }, []);

  const notify = (m) => { setToast(m); setTimeout(() => setToast(''), 3500); };

  async function refresh() {
    setLoading(true);
    try { setTrips(await api.listTrips()); } catch (e) { notify(e.message); }
    setLoading(false);
  }

  useEffect(() => { if (session) refresh(); }, [session]);

  async function remove(t) {
    if (!confirm(`Delete "${t.itinerary?.title || t.destination}"?`)) return;
    try { await api.deleteTrip(t.id); setTrips((x) => x.filter((y) => y.id !== t.id)); notify('Trip deleted'); }
    catch (e) { notify(e.message); }
  }

  if (session === undefined) return <p className="muted center">Loading…</p>;
  if (!session) return <Auth />;

  return (
    <div className="shell">
      <header className="topbar no-print">
        <button className="brand" onClick={() => { setView('home'); refresh(); }}>Wayfare</button>
        <div className="top-actions">
          <button className="btn primary" onClick={() => setView('plan')}>New trip</button>
          <button className="link" onClick={() => supabase.auth.signOut()}>Sign out</button>
        </div>
      </header>
      <div className="page">
        {view === 'home' && (
          <>
            <h1 className="page-title no-print">Your trips</h1>
            <TripList trips={trips} loading={loading} onNew={() => setView('plan')}
              onOpen={(t) => { setTrip(t); setView('trip'); }} onDelete={remove} />
          </>
        )}
        {view === 'plan' && (
          <Planner onCancel={() => setView('home')} notify={notify}
            onCreated={(t) => { setTrip(t); setView('trip'); }} />
        )}
        {view === 'trip' && trip && (
          <Itinerary key={trip.id} trip={trip} notify={notify}
            onBack={() => { setView('home'); refresh(); }} />
        )}
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
