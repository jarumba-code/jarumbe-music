# Jarumba Mobile Frontend

## Install

npm install

## Environment setup

Expo SDK 57 reads `EXPO_PUBLIC_*` variables from a local `.env` file in this folder at runtime. The app expects the public Supabase values only.

1. Copy the example file:
   `cp .env.example .env`
2. Fill in the public values in `.env`:
   - `EXPO_PUBLIC_SUPABASE_URL=https://vmtttyobdjluxujlermw.supabase.co`
   - `EXPO_PUBLIC_SUPABASE_ANON_KEY=replace-with-public-anon-key`
   - `EXPO_PUBLIC_API_BASE_URL=https://jarumbe-music-production.up.railway.app`
3. Keep the real Supabase anon key out of source control. Do not commit `.env`.

Do not add Supabase service-role keys, database passwords, Jamendo credentials, or private Railway secrets to the mobile app.

## Run locally

npx expo start -c

## Android

npx expo run:android

## Auth

Google sign-in uses the Supabase **PKCE authorization-code flow** end to end:

1. `supabase.auth.signInWithOAuth({ provider: 'google', redirectTo, skipBrowserRedirect: true })`
   returns a Supabase authorize URL carrying a `code_challenge`
   (`auth.flowType` is `'pkce'` in `lib/api.ts`; the auth-js default is `'implicit'`).
2. `expo-web-browser` opens that URL and waits for the native redirect
   `jarumba://auth/callback?code=...` (the `jarumba` scheme from `app.json`).
3. `parseOAuthCallback()` reads the authorization code from the **query string**
   and `supabase.auth.exchangeCodeForSession(code, { flowId })` trades it for a
   session. The `flowId` returned by `signInWithOAuth()` selects the code
   verifier stored locally for that flow.

Tokens in a URL fragment (`#access_token=...`) mean the implicit flow was used;
the app reports that as an explicit callback error instead of accepting it.

The app stores the Supabase session (and the short-lived PKCE verifier) in
SecureStore and sends the access token as a bearer token to FastAPI.
OAuth diagnostics log callback structure only (scheme, host, port, path and
parameter names) - never parameter values.

## Audio

Audio playback is not wired yet. When a player is added, prefer the current
SDK 57 audio package (`expo-audio` / `expo-video`) instead of the legacy
`expo-av` package, and use the provider streaming URL exposed by the API.

## Download permission

The UI only renders download affordances when `download_allowed` is true from the backend. When false, the affordance is not shown.
