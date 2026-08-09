// Placeholder data mirroring the approved mockup, used until the real
// FastAPI backend (owned by the trading-simulation teammate) is wired up.
// Every page falls back to these fixtures only if the live API call fails.
import { generateCandles } from './generateCandles';
import type { PersonaProfile } from '../api/persona';
import type { Holding } from '../api/portfolio';
import type { ReallocationRow, PastRecommendation } from '../api/recommendation';
import type { NewsItem } from '../api/news';

export const PERSONA_FIXTURE: PersonaProfile = {
  archetype: 'Growth-Oriented Realist',
  summary:
    "A high risk tolerance (72/100) means you're comfortable riding out volatility for upside, and comparatively low loss aversion (58/100) means drawdowns don't push you to panic-sell. Moderate regret aversion (41/100) still keeps you from chasing every hot stock.",
  riskTolerance: 72,
  lossAversion: 58,
  regretAversion: 41,
};

const HOLDING_BASE = [
  { ticker: 'JKH.N0000', name: 'John Keells Holdings', sector: 'Diversified', weightPct: 22, changePct: 13.2 },
  { ticker: 'COMB.N0000', name: 'Commercial Bank', sector: 'Banking', weightPct: 18, changePct: -39.8 },
  { ticker: 'LOLC.N0000', name: 'LOLC Holdings', sector: 'Diversified Fin.', weightPct: 16, changePct: -9.8 },
  { ticker: 'DIAL.N0000', name: 'Dialog Axiata', sector: 'Telecom', weightPct: 14, changePct: 4.9 },
  { ticker: 'HHL.N0000', name: 'Hemas Holdings', sector: 'Diversified', weightPct: 15, changePct: 7.7 },
  { ticker: 'SAMP.N0000', name: 'Sampath Bank', sector: 'Banking', weightPct: 15, changePct: 13.3 },
];

export const PORTFOLIO_FIXTURE: Holding[] = HOLDING_BASE.map((holding) => ({
  ...holding,
  candles: generateCandles(holding.ticker, holding.changePct),
}));

export const RECOMMENDATION_FIXTURE: ReallocationRow[] = [
  { ticker: 'JKH.N0000', name: 'John Keells Holdings', currentPct: 22, recommendedPct: 18, currentValue: null, recommendedValue: null, currentQty: null, recommendedQty: null },
  { ticker: 'COMB.N0000', name: 'Commercial Bank', currentPct: 18, recommendedPct: 22, currentValue: null, recommendedValue: null, currentQty: null, recommendedQty: null },
  { ticker: 'LOLC.N0000', name: 'LOLC Holdings', currentPct: 16, recommendedPct: 16, currentValue: null, recommendedValue: null, currentQty: null, recommendedQty: null },
  { ticker: 'DIAL.N0000', name: 'Dialog Axiata', currentPct: 14, recommendedPct: 10, currentValue: null, recommendedValue: null, currentQty: null, recommendedQty: null },
  { ticker: 'HHL.N0000', name: 'Hemas Holdings', currentPct: 15, recommendedPct: 14, currentValue: null, recommendedValue: null, currentQty: null, recommendedQty: null },
  { ticker: 'SAMP.N0000', name: 'Sampath Bank', currentPct: 15, recommendedPct: 20, currentValue: null, recommendedValue: null, currentQty: null, recommendedQty: null },
];

export const PAST_RECOMMENDATIONS_FIXTURE: PastRecommendation[] = [
  {
    date: 'Jun 18, 2026',
    description:
      'Shifted weight from JKH and Dial into Sampath and Combank ahead of a rate move.',
    rating: 4,
  },
  {
    date: 'May 4, 2026',
    description: 'First rebalance after onboarding, evening out sector concentration in banking.',
    rating: 3,
  },
];

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();

export const NEWS_FIXTURE: NewsItem[] = [
  {
    ticker: 'COMB.N0000',
    category: 'micro',
    headline: 'Commercial Bank of Ceylon reports steady loan growth in Q2',
    content:
      'Commercial Bank of Ceylon posted steady loan growth in the second quarter, supported by improving demand across its retail and SME segments.',
    source: 'Banking Desk',
    publishedDate: hoursAgo(2),
  },
  {
    ticker: 'DIAL.N0000',
    category: 'micro',
    headline: 'Dialog Axiata expands 5G rollout to Kandy and Galle',
    content:
      'Dialog Axiata extended its 5G network coverage to Kandy and Galle, marking the next phase of its nationwide rollout.',
    source: 'Telecom Wire',
    publishedDate: hoursAgo(4),
  },
  {
    category: 'macro',
    headline: 'Central Bank holds policy rate steady amid inflation watch',
    content:
      'The Central Bank kept its benchmark policy rate unchanged, signalling a cautious stance as it monitors inflation trends.',
    source: 'Macro Desk',
    publishedDate: hoursAgo(5),
  },
  {
    ticker: 'JKH.N0000',
    category: 'micro',
    headline: 'John Keells Holdings announces new leisure sector investment',
    content:
      'John Keells Holdings unveiled a new investment in its leisure segment, aiming to capitalise on the recovery in tourism.',
    source: 'Markets Desk',
    publishedDate: hoursAgo(6),
  },
  {
    category: 'macro',
    headline: 'Rupee strengthens against the dollar on remittance inflows',
    content:
      'The Sri Lankan rupee appreciated against the US dollar, buoyed by stronger worker remittance inflows.',
    source: 'Macro Desk',
    publishedDate: hoursAgo(9),
  },
  {
    ticker: 'LOLC.N0000',
    category: 'micro',
    headline: 'LOLC Holdings sees continued growth across microfinance arm',
    content:
      'LOLC Holdings reported continued expansion in its microfinance business, driven by rising demand in regional markets.',
    source: 'Finance Wire',
    publishedDate: hoursAgo(24),
  },
  {
    ticker: 'HHL.N0000',
    category: 'micro',
    headline: 'Hemas Holdings posts stable earnings in consumer segment',
    content:
      'Hemas Holdings delivered stable earnings in its consumer segment, with resilient demand for personal care products.',
    source: 'Markets Desk',
    publishedDate: hoursAgo(48),
  },
  {
    category: 'macro',
    headline: 'CSE All-Share Index closes higher on banking sector gains',
    content:
      'The Colombo Stock Exchange All-Share Index closed higher, led by gains in banking sector counters.',
    source: 'Market Wrap',
    publishedDate: hoursAgo(50),
  },
];
