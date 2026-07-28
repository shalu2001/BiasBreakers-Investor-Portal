// Single source of truth for the app's color palette (matches the approved
// "SL20 Invest" mockup). Change a value here and every page picks it up —
// components should never hardcode hex codes, only reference these tokens
// (either `colors.primary` in JS/inline styles, or `var(--color-primary)` in CSS).
export const colors = {
  bg: '#0d1017',
  surface: '#151924',
  border: '#262b38',
  text: '#e8e9ed',
  textMuted: '#9aa1ad',

  accent: '#d9a441',
  accentHover: '#c6913a',
  accentText: '#f0c877',

  success: '#34d399',
  danger: '#f2777a',
} as const;

export type ColorToken = keyof typeof colors;

const toCssVarName = (token: string) =>
  `--color-${token.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()}`;

// Mirrors every token above onto :root as a CSS custom property, so plain
// CSS files can use var(--color-primary) etc. without duplicating values.
export function applyColorTheme() {
  const root = document.documentElement;
  for (const [token, value] of Object.entries(colors)) {
    root.style.setProperty(toCssVarName(token), value);
  }
}
