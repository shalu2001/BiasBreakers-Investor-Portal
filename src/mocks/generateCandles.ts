import type { Candle } from '../api/portfolio';

function hashSeed(input: string): number {
  let h = 0;
  for (let i = 0; i < input.length; i++) {
    h = (Math.imul(31, h) + input.charCodeAt(i)) | 0;
  }
  return h >>> 0;
}

function mulberry32(seed: number) {
  let state = seed;
  return function random() {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Deterministic placeholder OHLC series ending at the stated overall % change —
// swap for real price history once the backend exposes it.
export function generateCandles(seed: string, changePct: number, count = 20): Candle[] {
  const random = mulberry32(hashSeed(seed));
  const startPrice = 100;
  const endPrice = startPrice * (1 + changePct / 100);
  const drift = (endPrice - startPrice) / count;
  const step = Math.max(Math.abs(drift), 1);

  const candles: Candle[] = [];
  let price = startPrice;
  const today = new Date();

  for (let i = 0; i < count; i++) {
    const open = price;
    const close = open + drift + (random() - 0.5) * step * 4;
    const high = Math.max(open, close) + random() * step * 2;
    const low = Math.min(open, close) - random() * step * 2;
    const date = new Date(today);
    date.setDate(today.getDate() - (count - i));

    candles.push({
      time: date.toISOString().slice(0, 10),
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
    });
    price = close;
  }

  candles[candles.length - 1].close = Number(endPrice.toFixed(2));
  return candles;
}
