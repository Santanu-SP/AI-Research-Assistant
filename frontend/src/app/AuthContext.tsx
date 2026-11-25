import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { AuthUser, authService } from '../services/auth.service';
import { ApiError } from '../services/api';

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  refreshUser: () => Promise<AuthUser | null>;
}

const AuthContext = createContext<AuthState | null>(null);

const INACTIVITY_RECHECK_INTERVAL_MS = 60_000;

export const SESSION_COOKIE_BLOCKED = 'session_cookie_blocked';
export const SESSION_COOKIE_BLOCKED_MESSAGE =
  'Your password was correct, but this browser blocked the sign-in cookie. Allow cookies for this site (or turn off cross-site tracking prevention for it) and try again.';

export const AuthProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const lastCheckedRef = useRef(0);

  const refreshUser = useCallback(async () => {
    try {
      const current = await authService.me();
      lastCheckedRef.current = Date.now();
      setUser(current);
      return current;
    } catch (error) {
      lastCheckedRef.current = Date.now();
      // Keep the current session mounted on transient network or server blips;
      // only real auth failures end the session.
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        setUser(null);
      }
      return null;
    }
  }, []);

  useEffect(() => {
    let active = true;
    authService.me().then((current) => {
      if (active) {
        lastCheckedRef.current = Date.now();
        setUser(current);
      }
    }).catch(() => {
      if (active) {
        lastCheckedRef.current = Date.now();
        setUser(null);
      }
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const expire = () => setUser(null);
    const onVisibilityChange = () => {
      if (
        document.visibilityState === 'visible'
        && Date.now() - lastCheckedRef.current > INACTIVITY_RECHECK_INTERVAL_MS
      ) {
        void refreshUser();
      }
    };
    window.addEventListener('auth:expired', expire);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.removeEventListener('auth:expired', expire);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const current = await authService.login(email, password);
    // Some browsers (Safari, Brave, private windows) silently drop a session
    // cookie that comes from another site. Check that the cookie was kept, so
    // the user gets a clear message now instead of being signed out on the
    // next page load.
    try {
      await authService.me();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw new ApiError('Sign-in cookie was blocked', 401, {
          error: { code: SESSION_COOKIE_BLOCKED, message: SESSION_COOKIE_BLOCKED_MESSAGE },
        });
      }
      // A network blip here should not undo a successful sign-in.
    }
    lastCheckedRef.current = Date.now();
    setUser(current);
  }, []);

  const logout = useCallback(async () => {
    await authService.logout();
    setUser(null);
  }, []);

  const logoutAll = useCallback(async () => {
    await authService.logoutAll();
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, loading, login, logout, logoutAll, refreshUser }}>{children}</AuthContext.Provider>;
};

export const useOptionalAuth = (): AuthState | null => useContext(AuthContext);

export const useAuth = (): AuthState => {
  const state = useContext(AuthContext);
  if (!state) throw new Error('AuthProvider is missing');
  return state;
};
