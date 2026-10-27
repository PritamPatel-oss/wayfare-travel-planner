import { useState } from 'react';
import { api } from './api';

const TYPE_LABEL = { attraction: 'Sight', food: 'Food', stay: 'Stay', transport: 'Travel' };

export default function Itinerary({ trip, onBack, notify }) {
  const [it, setIt] = useState(trip.itinerary);
  const [active, setActive] = useState(0);
  const [edit, setEdit] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState('');
  const [instruction, setInstruction] = useState('');

  const cur = it?.currency || 'INR';
  const money = (n) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(n || 0);
  const dayCost = (d) => (d?.activities || []).reduce((s, a) => s + (Number(a.cost) || 0), 0);
  const total = (it?.days || []).reduce((s, d) => s + dayCost(d), 0);
  const day = it?.days?.[Math.min(active, (it?.days?.length || 1) - 1)];
  const idx = it?.days ? it.days.indexOf(day) : -1;

  const patchDay = (fn) => { setIt((p) => ({ ...p, days: p.days.map((d, i) => (i === idx ? fn(d) : d)) })); setDirty(true); };
  const patchAct = (j, p) => patchDay((d) => ({ ...d, activities: d.activities.map((a, k) => (k === j ? { ...a, ...p } : a)) }));
  const removeAct = (j) => patchDay((d) => ({ ...d, activities: d.activities.filter((_, k) => k !== j) }));
  const addAct = () => patchDay((d) => ({ ...d, activities: [...d.activities, { time: '12:00', period: 'afternoon', type: 'attraction', title: 'New stop', description: '', location: '', cost: 0 }] }));

  async function save() {
    setBusy('save');
    try { await api.updateTrip(trip.id, it); setDirty(false); notify('Changes saved'); }
    catch (e) { notify(e.message); }
    setBusy('');
  }

  async function regenerate() {
    setBusy('regen');
    try {
      const fresh = await api.regenDay({
        preferences: trip.preferences,
        day_number: day.day,
        other_places: it.days.filter((d) => d !== day).flatMap((d) => d.activities.map((a) => a.title)),
        instruction: instruction.trim() || null,
      });
      patchDay(() => fresh);
      setInstruction('');
      notify(`Day ${day.day} rebuilt`);
    } catch (e) { notify(e.message); }
    setBusy('');
  }

  function back() { if (!dirty || confirm('You have unsaved changes. Leave anyway?')) onBack(); }

  return (
    <div className="itin">
      <div className="itin-head no-print">
        <button className="link" onClick={back}>Back to trips</button>
        <div className="top-actions">
          <button className="btn" onClick={() => window.print()}>Download PDF</button>
          <button className="btn primary" onClick={save} disabled={!dirty || busy === 'save'}>{busy === 'save' ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}</button>
        </div>
      </div>

      <header className="hero" style={it.cover?.url ? { backgroundImage: `linear-gradient(180deg, rgba(8,28,35,.15), rgba(8,28,35,.85)), url(${it.cover.url})` } : undefined}>
        <h1>{it.title}</h1>
        <p>{it.summary}</p>
        <dl className="facts">
          <div><dt>Destination</dt><dd>{trip.destination}</dd></div>
          <div><dt>Length</dt><dd>{it.days.length} {it.days.length === 1 ? 'day' : 'days'}</dd></div>
          <div><dt>Estimated cost</dt><dd>{money(total)}</dd></div>
        </dl>
      </header>

      <nav className="tabs no-print" aria-label="Days">
        {it.days.map((d, i) => (
          <button key={d.day} className={'tab' + (i === idx ? ' on' : '')} onClick={() => setActive(i)}>Day {d.day}</button>
        ))}
      </nav>

      <section className="day no-print">
        <div className="day-head">
          <div>
            <h2>Day {day.day}: {day.theme}</h2>
            <p className="muted">{money(dayCost(day))} for the day</p>
          </div>
          <button className={'btn' + (edit ? ' primary' : '')} onClick={() => setEdit(!edit)}>{edit ? 'Done editing' : 'Edit day'}</button>
        </div>
        {day.image?.url && <img className="day-img" src={day.image.url} alt={`${trip.destination}: ${day.theme}`} />}
        {day.image?.credit && <p className="credit">Photo by {day.image.credit} on Unsplash</p>}

        <ol className="timeline">
          {day.activities.map((a, j) => (
            <li key={j} className={'stop ' + a.type}>
              <div className="when">{edit ? <input aria-label="Time" value={a.time} onChange={(e) => patchAct(j, { time: e.target.value })} /> : a.time}</div>
              <div className="what">
                <span className="tag">{TYPE_LABEL[a.type]}</span>
                {edit ? (
                  <>
                    <input aria-label="Title" value={a.title} onChange={(e) => patchAct(j, { title: e.target.value })} />
                    <textarea aria-label="Description" rows={2} value={a.description} onChange={(e) => patchAct(j, { description: e.target.value })} />
                    <div className="row">
                      <input aria-label="Location" className="grow" value={a.location} onChange={(e) => patchAct(j, { location: e.target.value })} />
                      <input aria-label="Cost" type="number" min={0} value={a.cost} onChange={(e) => patchAct(j, { cost: e.target.value })} />
                      <button className="link danger" onClick={() => removeAct(j)}>Remove</button>
                    </div>
                  </>
                ) : (
                  <>
                    <h3>{a.title}</h3>
                    <p>{a.description}</p>
                    <p className="meta">
                      {a.location && (
                        <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(a.title + ' ' + a.location + ' ' + trip.destination)}`} target="_blank" rel="noreferrer">{a.location}</a>
                      )}
                      {a.cost > 0 && <span className="cost">{money(a.cost)}</span>}
                    </p>
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>
        {edit && <button className="btn" onClick={addAct}>Add a stop</button>}

        <div className="regen">
          <label className="grow">Not happy with this day?
            <input placeholder="e.g. Add more street food and skip museums" value={instruction} onChange={(e) => setInstruction(e.target.value)} />
          </label>
          <button className="btn" onClick={regenerate} disabled={busy === 'regen'}>{busy === 'regen' ? 'Rebuilding…' : `Rebuild day ${day.day}`}</button>
        </div>
      </section>

      {it.tips?.length > 0 && (
        <section className="tips">
          <h2>Good to know</h2>
          <ul>{it.tips.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </section>
      )}

      <section className="print-only">
        {it.days.map((d) => (
          <div key={d.day} className="print-day">
            <h2>Day {d.day}: {d.theme} ({money(dayCost(d))})</h2>
            <ul>{d.activities.map((a, k) => <li key={k}><strong>{a.time} {a.title}</strong>, {a.description} {a.location && `(${a.location})`}</li>)}</ul>
          </div>
        ))}
      </section>
    </div>
  );
}
