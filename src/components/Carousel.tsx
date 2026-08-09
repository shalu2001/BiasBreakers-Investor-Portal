import { Children, useCallback, useEffect, useRef } from 'react';
import styles from './Carousel.module.css';

interface CarouselProps {
  children: React.ReactNode;
  /** auto-advance interval in ms; set 0 to disable auto-scroll */
  intervalMs?: number;
  ariaLabel?: string;
}

// Self-advancing horizontal carousel: three items per screen, moves on its own,
// pauses on hover/focus, has prev/next arrows for manual control, and respects
// prefers-reduced-motion (auto-scroll off). Each child is measured so a step
// lands exactly one card along.
export function Carousel({ children, intervalMs = 3800, ariaLabel }: CarouselProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const paused = useRef(false);

  const step = useCallback((dir: 1 | -1) => {
    const el = trackRef.current;
    if (!el) return;
    const card = el.querySelector<HTMLElement>('[data-carousel-item]');
    const gap = parseFloat(getComputedStyle(el).columnGap || '20') || 20;
    const amount = card ? card.offsetWidth + gap : el.clientWidth * 0.8;
    const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 2;
    const atStart = el.scrollLeft <= 2;
    if (dir === 1 && atEnd) {
      el.scrollTo({ left: 0, behavior: 'smooth' }); // loop to start
    } else if (dir === -1 && atStart) {
      el.scrollTo({ left: el.scrollWidth, behavior: 'smooth' });
    } else {
      el.scrollBy({ left: amount * dir, behavior: 'smooth' });
    }
  }, []);

  useEffect(() => {
    if (!intervalMs) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const id = window.setInterval(() => {
      if (!paused.current) step(1);
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs, step]);

  const items = Children.toArray(children);

  return (
    <div
      className={styles.wrap}
      onMouseEnter={() => (paused.current = true)}
      onMouseLeave={() => (paused.current = false)}
      onFocusCapture={() => (paused.current = true)}
      onBlurCapture={() => (paused.current = false)}
    >
      <button
        type="button"
        className={`${styles.arrow} ${styles.arrowLeft}`}
        onClick={() => step(-1)}
        aria-label="Previous"
      >
        ‹
      </button>

      <div ref={trackRef} className={styles.track} role="region" aria-label={ariaLabel}>
        {items.map((child, i) => (
          <div key={i} className={styles.item} data-carousel-item>
            {child}
          </div>
        ))}
      </div>

      <button
        type="button"
        className={`${styles.arrow} ${styles.arrowRight}`}
        onClick={() => step(1)}
        aria-label="Next"
      >
        ›
      </button>
    </div>
  );
}
