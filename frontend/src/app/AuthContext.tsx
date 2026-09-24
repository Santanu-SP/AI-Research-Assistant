import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { AuthUser, authService } from '../services/auth.service';

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<AuthUser | null>;
}

const AuthContext = createContext<AuthState | null>(null);

export const AuthProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    authService.me().then((current) => {
      if (active) setUser(current);
    }).catch(() => {
      if (active) setUser(null);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const expire = () => setUser(null);
    window.addEventListener('auth:expired', expire);
    return () => window.removeEventListener('auth:expired', expire);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const current = await authService.login(email, password);
    setUser(current);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const current = await authService.me();
      setUser(current);
      return current;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  const logout = useCallback(async () => {
    await authService.logout();
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthState => {
  const state = useContext(AuthContext);
  if (!state) throw new Error('AuthProvider is missing');
  return state;
};
