// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { authService } from './auth.service';

const popupStub = () => {
  const popup = {
    closed: false,
    close: vi.fn(() => { popup.closed = true; }),
    focus: vi.fn(),
  };
  return popup;
};

const dispatchGoogleMessage = (source: object, origin: string, data: unknown) => {
  const event = new MessageEvent('message', { data, origin });
  Object.defineProperty(event, 'source', { value: source });
  window.dispatchEvent(event);
};

describe('Google authentication popup', () => {
  const enableGoogleAuth = () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ enabled: true }),
    }));
  };

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('ignores messages from an unexpected origin and accepts the expected success message', async () => {
    enableGoogleAuth();
    const popup = popupStub();
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
    const result = authService.startGoogleLogin();
    await new Promise((resolve) => setTimeout(resolve, 0));
    let settled = false;
    void result.finally(() => { settled = true; });

    dispatchGoogleMessage(popup, 'https://malicious.example', { type: 'google-auth-success' });
    await Promise.resolve();
    expect(settled).toBe(false);

    dispatchGoogleMessage(popup, window.location.origin, { type: 'google-auth-success' });
    await expect(result).resolves.toBeUndefined();
    expect(popup.close).toHaveBeenCalledOnce();
  });

  it('rejects and cleans up when the user closes the popup', async () => {
    enableGoogleAuth();
    vi.useFakeTimers();
    const popup = popupStub();
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
    const result = authService.startGoogleLogin();
    const rejection = expect(result).rejects.toThrow('Google sign-in was cancelled.');

    popup.closed = true;
    await vi.advanceTimersByTimeAsync(400);
    await rejection;
  });

  it('reports a blocked popup without starting a polling timer', async () => {
    enableGoogleAuth();
    const timer = vi.spyOn(window, 'setInterval');
    vi.spyOn(window, 'open').mockReturnValue(null);

    await expect(authService.startGoogleLogin()).rejects.toThrow('popup was blocked');
    expect(timer).not.toHaveBeenCalled();
  });
});
