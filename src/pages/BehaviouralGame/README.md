# Behavioural Game (React port)

The behavioural-preference onboarding game, ported from the standalone
HTML/CSS/JS instrument into React + TypeScript, styled with the portal's theme
tokens (`--color-*`, `--font-*`) and reusing the shared `CandlestickChart`
(lightweight-charts). **Self-contained** — no existing portal files were modified.

## Files
- `BehaviouralGamePage.tsx` — screen orchestrator + Start / Trading / Transition / Events / Results.
- `AllocationSlider.tsx` — the continuous position dial (used in trading and the event round).
- `GameCandles.tsx` — adapts the game backend's OHLC to the shared `CandlestickChart`.
- `GameTour.tsx` — first-trade spotlight tutorial (targets elements via `data-tour`).
- `HelpModal.tsx` — "how the numbers work" (money mechanics only).
- `game.module.css` — all styles, mapped to the shared theme tokens.
- `../../api/behaviouralGame.ts` — typed axios wrappers for the FastAPI game engine.

## Wire it up (one line — do this yourself in `App.tsx`)
```tsx
import { BehaviouralGamePage } from './pages/BehaviouralGame/BehaviouralGamePage';

// inside <Routes>, as a full-screen route (outside <AppLayout>, like /login):
<Route path="/behavioural-game" element={<BehaviouralGamePage />} />
```

## Environment
The game talks to its own FastAPI backend (the trading engine + estimators),
separate from the portal API. Add to `.env` (or `.env.local`):
```
VITE_GAME_API_BASE_URL=http://127.0.0.1:8000
```
If unset it defaults to `http://127.0.0.1:8000`. Start the backend from
`behavioural-simulation/backend`:
```
uvicorn app:app --reload
```
(The backend already sends permissive CORS headers, so the Vite dev server can
call it during development.)

## Type-check / build
```
npm install     # if not already
npm run build   # runs tsc -b + vite build
```
