import { API_BASE_URL, apiErrorMessage, apiRequest } from './api';

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export const authService = {
  register: (name: string, email: string, password: string) =>
    apiRequest<AuthUser>('/auth/register', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    }),
  login: (email: string, password: string) =>
    apiRequest<AuthUser>('/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    }),
  me: () => apiRequest<AuthUser>('/auth/me'),
  logout: () => apiRequest<void>('/auth/logout', { method: 'POST' }),
  startGoogleLogin: () => window.location.assign(`${API_BASE_URL}/auth/google/start`),
};

export const authErrorMessage = apiErrorMessage;
