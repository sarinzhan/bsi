import { useState, type FormEvent } from 'react';
import { useCurrentUser } from '../auth';

export default function LoginPage() {
  const { login, error: sessionError } = useCurrentUser();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={submit} aria-labelledby="login-h">
        <div className="logo">
          <div className="logo-mark">&lt;/&gt;</div>
          <span>BSI</span>
        </div>
        <h1 id="login-h">Sign in</h1>
        <div className="field">
          <label htmlFor="login-user">User name</label>
          <input id="login-user" className="mono" autoComplete="username" autoCapitalize="none" spellCheck={false}
            value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        </div>
        <div className="field">
          <label htmlFor="login-pass">Password</label>
          <input id="login-pass" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {(error || sessionError) && <p className="form-error" role="alert">{error || sessionError}</p>}
        <button type="submit" className="btn primary auth-submit" disabled={busy || !username.trim() || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="muted auth-note">No account? Ask an admin to add you on the Users page.</p>
      </form>
    </div>
  );
}
