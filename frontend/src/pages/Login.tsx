import React, { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { AuthShell, authInputClass, authLabelClass } from '../components/auth/AuthShell';
import { useAuth } from '../app/AuthContext';
import { authErrorMessage, authService } from '../services/auth.service';

export const LoginPage: React.FC = () => {
  const { user, login, refreshUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/research/new" replace />;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim() || !password) { setError('Enter your email and password.'); return; }
    setBusy(true); setError(null);
    try {
      await login(email, password);
      navigate('/research/new', { replace: true });
    } catch (cause) {
      setError(authErrorMessage(cause, 'Unable to sign in. Check your connection and try again.'));
    } finally { setBusy(false); }
  };

  const loginWithGoogle = async () => {
    setBusy(true); setError(null);
    try {
      await authService.startGoogleLogin();
      const current = await refreshUser();
      if (!current) throw new Error('Google sign-in could not restore your session. Please try again.');
      navigate('/research/new', { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Google sign-in was not completed. Please try again.');
    } finally { setBusy(false); }
  };

  const oauthError = searchParams.get('oauthError');
  const oauthMessage = oauthError ? 'Google sign-in was not completed. Please try again or use email and password.' : null;

  return <AuthShell title="Welcome back" description="Sign in to continue your research.">
    <form onSubmit={(event) => void submit(event)} className="space-y-4">
      {location.state?.registered && <p className="text-sm text-[#163328] bg-[#f1f6f3] rounded-md p-3">Account created. Sign in to continue.</p>}
      {oauthMessage && <p role="alert" className="text-sm text-[#b91c1c] bg-[#fee2e2]/50 rounded-md p-3">{oauthMessage}</p>}
      {error && <p role="alert" className="text-sm text-[#b91c1c] bg-[#fee2e2]/50 rounded-md p-3">{error}</p>}
      <div><label htmlFor="login-email" className={authLabelClass}>Email</label><input id="login-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className={authInputClass} /></div>
      <div><label htmlFor="login-password" className={authLabelClass}>Password</label><input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} className={authInputClass} /></div>
      <button type="submit" disabled={busy} className="w-full rounded-md bg-[#163328] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#214f40] disabled:opacity-60">{busy ? 'Signing in…' : 'Login'}</button>
      <div className="flex items-center gap-3 text-xs text-[#929792]"><span className="h-px flex-1 bg-[#e5e7e4]" />or<span className="h-px flex-1 bg-[#e5e7e4]" /></div>
      <button type="button" disabled={busy} onClick={() => void loginWithGoogle()} className="w-full rounded-md border border-[#d0d7d2] bg-white px-4 py-2.5 text-sm font-medium text-[#181a18] hover:bg-[#fafaf8] disabled:opacity-60 inline-flex items-center justify-center gap-2">
        <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4"><path fill="#4285F4" d="M21.35 12.23c0-.71-.06-1.39-.18-2.05H12v3.88h5.24a4.48 4.48 0 0 1-1.94 2.94v2.52h3.14c1.84-1.69 2.91-4.19 2.91-7.29Z"/><path fill="#34A853" d="M12 21.75c2.63 0 4.84-.87 6.45-2.35l-3.14-2.52c-.87.59-1.99.94-3.31.94-2.54 0-4.69-1.71-5.46-4.01H3.3v2.6A9.75 9.75 0 0 0 12 21.75Z"/><path fill="#FBBC05" d="M6.54 13.81a5.87 5.87 0 0 1 0-3.62V7.6H3.3a9.75 9.75 0 0 0 0 8.81l3.24-2.6Z"/><path fill="#EA4335" d="M12 6.18c1.43 0 2.71.49 3.72 1.45l2.79-2.79C16.84 3.28 14.63 2.25 12 2.25A9.75 9.75 0 0 0 3.3 7.6l3.24 2.59C7.31 7.89 9.46 6.18 12 6.18Z"/></svg>
        Continue with Google
      </button>
      <p className="text-center text-xs text-[#6b706c]">New here? <Link to="/register" className="font-medium text-[#163328] hover:underline">Create an account</Link></p>
    </form>
  </AuthShell>;
};
