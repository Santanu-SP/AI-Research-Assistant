import React, { useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AuthShell, authInputClass, authLabelClass } from '../components/auth/AuthShell';
import { useAuth } from '../app/AuthContext';
import { authErrorMessage } from '../services/auth.service';

export const LoginPage: React.FC = () => {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
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

  return <AuthShell title="Welcome back" description="Sign in to continue your research.">
    <form onSubmit={(event) => void submit(event)} className="space-y-4">
      {location.state?.registered && <p className="text-sm text-[#163328] bg-[#f1f6f3] rounded-md p-3">Account created. Sign in to continue.</p>}
      {error && <p role="alert" className="text-sm text-[#b91c1c] bg-[#fee2e2]/50 rounded-md p-3">{error}</p>}
      <div><label htmlFor="login-email" className={authLabelClass}>Email</label><input id="login-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className={authInputClass} /></div>
      <div><label htmlFor="login-password" className={authLabelClass}>Password</label><input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} className={authInputClass} /></div>
      <button type="submit" disabled={busy} className="w-full rounded-md bg-[#163328] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#214f40] disabled:opacity-60">{busy ? 'Signing in…' : 'Login'}</button>
      <p className="text-center text-xs text-[#6b706c]">New here? <Link to="/register" className="font-medium text-[#163328] hover:underline">Create an account</Link></p>
    </form>
  </AuthShell>;
};
