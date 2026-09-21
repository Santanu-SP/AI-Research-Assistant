import React, { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { AuthShell, authInputClass, authLabelClass } from '../components/auth/AuthShell';
import { useAuth } from '../app/AuthContext';
import { authErrorMessage, authService } from '../services/auth.service';

export const RegisterPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/research/new" replace />;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !email.trim() || !password || !confirmPassword) { setError('Complete all fields.'); return; }
    if (password.length < 8) { setError('Use at least 8 characters for your password.'); return; }
    if (password !== confirmPassword) { setError('Passwords do not match.'); return; }
    setBusy(true); setError(null);
    try {
      await authService.register(name.trim(), email.trim(), password);
      navigate('/login', { replace: true, state: { registered: true } });
    } catch (cause) {
      setError(authErrorMessage(cause, 'Unable to create your account. Try again.'));
    } finally { setBusy(false); }
  };

  return <AuthShell title="Create your account" description="Keep your documents and research in your own workspace.">
    <form onSubmit={(event) => void submit(event)} className="space-y-4">
      {error && <p role="alert" className="text-sm text-[#b91c1c] bg-[#fee2e2]/50 rounded-md p-3">{error}</p>}
      <div><label htmlFor="register-name" className={authLabelClass}>Name</label><input id="register-name" autoComplete="name" required value={name} onChange={(event) => setName(event.target.value)} className={authInputClass} /></div>
      <div><label htmlFor="register-email" className={authLabelClass}>Email</label><input id="register-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className={authInputClass} /></div>
      <div><label htmlFor="register-password" className={authLabelClass}>Password</label><input id="register-password" type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} className={authInputClass} /></div>
      <div><label htmlFor="register-confirm" className={authLabelClass}>Confirm password</label><input id="register-confirm" type="password" autoComplete="new-password" required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className={authInputClass} /></div>
      <button type="submit" disabled={busy} className="w-full rounded-md bg-[#163328] px-4 py-2.5 text-sm font-medium text-white hover:bg-[#214f40] disabled:opacity-60">{busy ? 'Creating account…' : 'Register'}</button>
      <p className="text-center text-xs text-[#6b706c]">Already have an account? <Link to="/login" className="font-medium text-[#163328] hover:underline">Login</Link></p>
    </form>
  </AuthShell>;
};
