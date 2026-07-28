// Matches the mockup: Roboto for body/UI text, JetBrains Mono for tickers
// and numeric figures (prices, percentages) so they align in tables/columns.
export const fonts = {
  body: `Roboto, system-ui, -apple-system, 'Segoe UI', sans-serif`,
  mono: `'JetBrains Mono', SFMono-Regular, ui-monospace, Menlo, Consolas, monospace`,
} as const;

export function applyFontTheme() {
  const root = document.documentElement;
  root.style.setProperty('--font-body', fonts.body);
  root.style.setProperty('--font-mono', fonts.mono);
}
