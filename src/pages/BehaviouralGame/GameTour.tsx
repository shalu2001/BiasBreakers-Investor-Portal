import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import styles from './game.module.css';

export interface TourStep { key: string; title: string; text: string }

// First-trade tutorial: a spotlight over a real on-screen element with a floating
// card, scroll-locked so the highlight can't drift. Targets are found by their
// data-tour="<key>" attribute (which survives CSS-module hashing).
export function GameTour({ steps, onDone }: { steps: TourStep[]; onDone: () => void }) {
  const [index, setIndex] = useState(0);
  const [spotStyle, setSpotStyle] = useState<CSSProperties>({ visibility: 'hidden' });
  const [cardStyle, setCardStyle] = useState<CSSProperties>({ visibility: 'hidden' });
  const cardRef = useRef<HTMLDivElement>(null);
  const step = steps[index];
  const last = index === steps.length - 1;

  const position = useCallback(() => {
    const target = document.querySelector<HTMLElement>(`[data-tour="${step.key}"]`);
    const card = cardRef.current;
    if (!target || !card) return;
    const r = target.getBoundingClientRect();
    const pad = 8, margin = 14, vw = window.innerWidth, vh = window.innerHeight;
    setSpotStyle({ top: r.top - pad, left: r.left - pad, width: r.width + pad * 2, height: r.height + pad * 2 });

    const cw = card.offsetWidth, ch = card.offsetHeight;
    const clampX = (x: number) => Math.max(10, Math.min(x, vw - cw - 10));
    const clampY = (y: number) => Math.max(10, Math.min(y, vh - ch - 10));
    let top: number, left: number;
    if (vh - r.bottom >= ch + margin) { top = r.bottom + margin; left = clampX(r.left + r.width / 2 - cw / 2); }
    else if (r.top >= ch + margin) { top = r.top - ch - margin; left = clampX(r.left + r.width / 2 - cw / 2); }
    else if (vw - r.right >= cw + margin) { left = r.right + margin; top = clampY(r.top + r.height / 2 - ch / 2); }
    else if (r.left >= cw + margin) { left = r.left - cw - margin; top = clampY(r.top + r.height / 2 - ch / 2); }
    else { left = clampX(vw / 2 - cw / 2); top = clampY(vh / 2 - ch / 2); }
    setCardStyle({ top, left, visibility: 'visible' });
  }, [step.key]);

  // Scroll each target into view, then measure (double rAF so layout settles).
  useLayoutEffect(() => {
    const target = document.querySelector<HTMLElement>(`[data-tour="${step.key}"]`);
    if (!target) { onDone(); return; }
    setCardStyle((s) => ({ ...s, visibility: 'hidden' }));
    target.scrollIntoView({ block: 'center', inline: 'nearest' });
    const id = requestAnimationFrame(() => requestAnimationFrame(position));
    return () => cancelAnimationFrame(id);
  }, [step.key, position, onDone]);

  // Lock page scrolling while the tour is up (programmatic scrollIntoView still works).
  useEffect(() => {
    const block = (e: Event) => e.preventDefault();
    const blockKeys = (e: KeyboardEvent) => {
      if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ', 'Spacebar'].includes(e.key)) e.preventDefault();
    };
    const opts = { passive: false, capture: true } as AddEventListenerOptions;
    window.addEventListener('wheel', block, opts);
    window.addEventListener('touchmove', block, opts);
    window.addEventListener('keydown', blockKeys, opts);
    window.addEventListener('scroll', position, true);
    window.addEventListener('resize', position);
    return () => {
      window.removeEventListener('wheel', block, opts);
      window.removeEventListener('touchmove', block, opts);
      window.removeEventListener('keydown', blockKeys, opts);
      window.removeEventListener('scroll', position, true);
      window.removeEventListener('resize', position);
    };
  }, [position]);

  return (
    <div className={styles.tour}>
      <div className={styles.tourSpot} style={spotStyle} />
      <div className={styles.tourCard} style={cardStyle} ref={cardRef}>
        <div className={styles.tourStep}>{index + 1} / {steps.length}</div>
        <h3>{step.title}</h3>
        <p>{step.text}</p>
        <div className={styles.tourActions}>
          <button type="button" className={styles.tourSkip} onClick={onDone}>Skip tour</button>
          <button type="button" className={styles.tourNext} onClick={() => (last ? onDone() : setIndex((i) => i + 1))}>
            {last ? 'Got it ✓' : 'Next →'}
          </button>
        </div>
      </div>
    </div>
  );
}
