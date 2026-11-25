# Deploying the frontend on Cloudflare Pages

The frontend runs on Cloudflare Pages and the API runs somewhere else (for example Render).
Sign-in uses an HttpOnly cookie called `ara_session`. If the browser talks to the API on
another site, that cookie is a **third-party cookie**, and Safari, Brave, Firefox in strict
mode and private windows block it. Users then sign in, look signed in, and are signed out on
the next page load.

The fix is the same-origin proxy in `frontend/functions/api/[[path]].ts`: the browser calls
`https://your-app.pages.dev/api/...`, and the Pages Function forwards the request (and
WebSockets) to the API. The cookie is then first-party and every browser keeps it.

## Settings in Cloudflare Pages

Set these in **Pages project → Settings → Environment variables** (Production, and Preview if
you use preview builds):

| Variable | Value | Why |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v1` | The built app calls the API through the proxy on its own origin. |
| `BACKEND_ORIGIN` | `https://your-backend.onrender.com` | Where the proxy forwards to. No path, no trailing slash. |

Build settings: root directory `frontend`, build command `npm run build`, output `dist`.

Fallbacks, so an older setup keeps working:

- If `BACKEND_ORIGIN` is missing but `VITE_API_BASE_URL` is an absolute URL, the proxy uses that
  URL's origin.
- If the app was built with an absolute cross-site `VITE_API_BASE_URL` and the browser drops the
  cookie at sign-in, the app checks `/api/v1/health` on its own origin. If the proxy answers, it
  switches to the proxy, signs in again and remembers the choice. If not, the login page explains
  that the browser blocked the sign-in cookie.

## Settings on the backend

| Variable | Value |
|---|---|
| `FRONTEND_URL` | `https://your-app.pages.dev` |
| `CORS_ORIGINS` | `["https://your-app.pages.dev"]` |
| `AUTH_COOKIE_SECURE` | `true` (the default in production) |
| `GOOGLE_REDIRECT_URI` | `https://your-app.pages.dev/api/v1/auth/google/callback` (only if Google sign-in is on) |

The Google redirect URI must go through the proxy too, and the same URL must be added to the
Google Cloud OAuth client.

## Quick check after a deploy

1. Open `https://your-app.pages.dev/api/v1/health`. It should return `{"status":"ok", ...}`.
2. Sign in on Safari (or an iPhone), reload the page, and open a project. You should stay signed
   in and see the live presence bar.
