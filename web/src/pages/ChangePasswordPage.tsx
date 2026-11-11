import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import { ApiError } from '../api/http';
import { useCurrentUser } from '../auth';

const MIN_LENGTH = 10;

/**
 * forced: the first sign-in after an admin set the password (or the default admin): nothing else works
 * until it is changed. Otherwise the "Change password" page from the sidebar.
 */
export default function ChangePasswordPage({ forced = false }: { forced?: boolean }) {
  const { user, reload, logout } = useCurrentUser();
  const navigate = useNavigate();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const problem =
    next && next.length < MIN_LENGTH ? `At least ${MIN_LENGTH} characters.`
    : again && next !== again ? 'The two new passwords are not the same.'
    : '';

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (problem) return;
    setError('');
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setAgain('');
      setDone(true);
      await reload();
      if (forced) navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401
        ? 'Your sign-in is no longer valid, so the password was NOT changed. Sign out and sign in again.'
        : err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const form = (
    <form className={forced ? 'card auth-card' : 'card settings-card narrow'} onSubmit={submit}
      aria-label={forced ? 'Pick your own password' : 'Change password'}>
      {forced && <h1>Pick your own password</h1>}
      {forced && (
        <p className="muted">
          Signed in as <b className="mono">{user?.id}</b> with a temporary password. Choose your own to continue.
        </p>
      )}
      <div className="field">
        <label htmlFor="pw-current">{forced ? 'Temporary password' : 'Current password'}</label>
        <input id="pw-current" type="password" autoComplete="current-password" value={current}
          onChange={(e) => setCurrent(e.target.value)} required autoFocus={forced} />
      </div>
      <div className="field">
        <label htmlFor="pw-new">New password</label>
        <input id="pw-new" type="password" autoComplete="new-password" value={next} minLength={MIN_LENGTH}
          onChange={(e) => { setNext(e.target.value); setDone(false); }} required aria-describedby="pw-hint" />
        <span id="pw-hint" className="muted" style={{ fontSize: 12 }}>At least {MIN_LENGTH} characters, not your user name.</span>
      </div>
      <div className="field">
        <label htmlFor="pw-again">New password again</label>
        <input id="pw-again" type="password" autoComplete="new-password" value={again}
          onChange={(e) => setAgain(e.target.value)} required />
      </div>
      {(problem || error) && <p className="form-error" role="alert">{problem || error}</p>}
      {done && !forced && <p className="ok-note" role="status">Password changed. Other browsers were signed out.</p>}
      <div className="settings-actions">
        <button type="submit" className="btn primary" disabled={busy || !current || !next || !again || !!problem}>
          {busy ? 'Saving…' : 'Save password'}
        </button>
        {forced && <button type="button" className="btn" onClick={() => void logout()}>Sign out</button>}
      </div>
    </form>
  );

  if (forced) return <div className="auth-page">{form}</div>;
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Change password</h1>
          <p>Signed in as <span className="mono">{user?.id}</span>. Changing it signs you out in your other browsers.</p>
        </div>
      </div>
      {form}
    </div>
  );
}
