import { useState } from 'react';
import { api } from './api';

const INTERESTS = ['Food', 'History', 'Nature', 'Adventure', 'Culture', 'Shopping', 'Nightlife', 'Beaches', 'Photography', 'Spiritual'];
const LEVELS = [['budget', 'Budget', 'Hostels, street food, public transport'], ['moderate', 'Moderate', 'Comfortable stays, mix of dining'], ['luxury', 'Luxury', 'Premium stays and experiences']];
const STYLES = [['relaxed', 'Relaxed', 'Few stops, slow pace'], ['balanced', 'Balanced', 'A bit of everything'], ['adventurous', 'Adventurous', 'Packed and offbeat']];

function Choice({ options, value, onChange }) {
  return (
    <div className="choices" role="radiogroup">
      {options.map(([v, label, hint]) => (
        <button type="button" key={v} role="radio" aria-checked={value === v}
          className={'choice' + (value === v ? ' on' : '')} onClick={() => onChange(v)}>
          <strong>{label}</strong><span>{hint}</span>
        </button>
      ))}
    </div>
  );
}

export default function Planner({ onCancel, onCreated, notify }) {
  const [f, setF] = useState({
    destination: '', days: 3, travelers: 2, budget_level: 'moderate', budget_amount: '',
    currency: 'INR', travel_style: 'balanced', interests: ['Food'], start_date: '', notes: '',
  });
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const toggle = (i) => set('interests', f.interests.includes(i) ? f.interests.filter((x) => x !== i) : [...f.interests, i]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    const prefs = {
      ...f,
      days: Number(f.days),
      travelers: Number(f.travelers),
      budget_amount: f.budget_amount === '' ? null : Number(f.budget_amount),
      start_date: f.start_date || null,
      notes: f.notes.trim() || null,
    };
    try {
      const itinerary = await api.generate(prefs);
      const saved = await api.createTrip({ destination: prefs.destination, days: prefs.days, preferences: prefs, itinerary });
      onCreated(saved);
    } catch (err) {
      notify(err.message);
      setBusy(false);
    }
  }

  return (
    <form className="planner" onSubmit={submit}>
      <h1 className="page-title">Plan a trip</h1>
      <div className="row">
        <label className="grow">Where to?<input required minLength={2} placeholder="Jaipur, Goa, Tokyo…" value={f.destination} onChange={(e) => set('destination', e.target.value)} /></label>
        <label>Days<input type="number" min={1} max={14} required value={f.days} onChange={(e) => set('days', e.target.value)} /></label>
        <label>Travelers<input type="number" min={1} max={20} required value={f.travelers} onChange={(e) => set('travelers', e.target.value)} /></label>
        <label>Start date<input type="date" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} /></label>
      </div>

      <fieldset><legend>Budget</legend>
        <Choice options={LEVELS} value={f.budget_level} onChange={(v) => set('budget_level', v)} />
        <div className="row">
          <label>Currency
            <select value={f.currency} onChange={(e) => set('currency', e.target.value)}><option>INR</option><option>USD</option><option>EUR</option></select>
          </label>
          <label className="grow">Total for the group (optional)<input type="number" min={0} placeholder="e.g. 30000" value={f.budget_amount} onChange={(e) => set('budget_amount', e.target.value)} /></label>
        </div>
      </fieldset>

      <fieldset><legend>Pace</legend>
        <Choice options={STYLES} value={f.travel_style} onChange={(v) => set('travel_style', v)} />
      </fieldset>

      <fieldset><legend>Interests</legend>
        <div className="chips">
          {INTERESTS.map((i) => (
            <button type="button" key={i} aria-pressed={f.interests.includes(i)} className={'chip' + (f.interests.includes(i) ? ' on' : '')} onClick={() => toggle(i)}>{i}</button>
          ))}
        </div>
      </fieldset>

      <label>Anything else?<textarea rows={3} maxLength={500} placeholder="Vegetarian food, travelling with parents, avoid long walks…" value={f.notes} onChange={(e) => set('notes', e.target.value)} /></label>

      <div className="row end">
        <button type="button" className="link" onClick={onCancel} disabled={busy}>Cancel</button>
        <button className="btn primary" disabled={busy}>{busy ? 'Building your itinerary… (10-20 seconds)' : 'Generate itinerary'}</button>
      </div>
    </form>
  );
}
