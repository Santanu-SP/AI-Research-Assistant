import { API_BASE_URL, apiErrorMessage, apiRequest } from './api';

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

type GoogleAuthMessage =
  | { type: 'google-auth-success' }
  | { type: 'google-auth-error'; error: string };

const isGoogleAuthMessage = (value: unknown): value is GoogleAuthMessage => {
  if (typeof value !== 'object' || value === null) return false;
  const message = value as Record<string, unknown>;
  if (message.type === 'google-auth-success') return Object.keys(message).length === 1;
  return message.type === 'google-auth-error'
    && typeof message.error === 'string'
    && Object.keys(message).every((key) => key === 'type' || key === 'error');
};

const startGoogleLogin = (): Promise<void> => {
  const popup = window.open(
    `${API_BASE_URL}/auth/google/start`,
    'google-oauth',
    'popup=yes,width=520,height=680,resizable=yes,scrollbars=yes',
  );
  if (!popup) return Promise.reject(new Error('Google sign-in popup was blocked. Allow popups and try again.'));

  return new Promise((resolve, reject) => {
    const expectedOrigin = window.location.origin;
    let closeTimer = 0;
    const cleanup = () => {
      window.removeEventListener('message', receiveMessage);
      if (closeTimer) window.clearInterval(closeTimer);
    };
    const finish = (error?: Error) => {
      cleanup();
      if (!popup.closed) popup.close();
      if (error) reject(error);
      else resolve();
    };
    const receiveMessage = (event: MessageEvent<unknown>) => {
      if (event.origin !== expectedOrigin || event.source !== popup || !isGoogleAuthMessage(event.data)) return;
      if (event.data.type === 'google-auth-success') finish();
      else finish(new Error('Google sign-in was not completed. Please try again or use email and password.'));
    };

    window.addEventListener('message', receiveMessage);
    closeTimer = window.setInterval(() => {
      if (popup.closed) finish(new Error('Google sign-in was cancelled.'));
    }, 400);
    popup.focus();
  });
};

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
  startGoogleLogin,
};

export const authErrorMessage = apiErrorMessage;
