import React, { useEffect, useRef } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { useAuth } from '../app/AuthContext';

export const GoogleAuthCompletePage: React.FC = () => {
  const { user, loading } = useAuth();
  const location = useLocation();
  const notified = useRef(false);
  const oauthError = new URLSearchParams(location.search).get('oauthError');
  const hasOpener = Boolean(window.opener && !window.opener.closed);

  useEffect(() => {
    if (loading || !hasOpener || notified.current) return;
    notified.current = true;
    const message = user && !oauthError
      ? { type: 'google-auth-success' }
      : { type: 'google-auth-error', error: oauthError || 'session_missing' };
    window.opener.postMessage(message, window.location.origin);
    window.close();
  }, [hasOpener, loading, oauthError, user]);

  if (loading || hasOpener) return <CenteredLoadingState label="Completing Google sign-in…" />;
  if (user && !oauthError) return <Navigate to="/research/new" replace />;
  return <Navigate to={`/login${location.search}`} replace />;
};
