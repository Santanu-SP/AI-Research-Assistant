import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { AuthUser, authService } from '../services/auth.service';

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
    } catch {
      lastCheckedRef.current = Date.now();
      setUser(null);
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
