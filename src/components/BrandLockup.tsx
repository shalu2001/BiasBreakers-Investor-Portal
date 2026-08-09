import styles from './BrandLockup.module.css';

interface BrandLockupProps {
  /** Wordmark font-size in px; the mark scales with it. Default 20. */
  size?: number;
  /** Render only the mark, without the "Cognivest" wordmark. */
  markOnly?: boolean;
  className?: string;
}

/**
 * Cognivest brand — horizontal lockup (mark + wordmark).
 * Extracted from the Cognivest Design System; uses `currentColor` so it
 * inherits the surrounding text color. This is the platform brand.
 */
export function BrandLockup({ size = 20, markOnly = false, className }: BrandLockupProps) {
  return (
    <span
      className={[styles.lockup, className].filter(Boolean).join(' ')}
      style={{ fontSize: size, gap: size * 0.42 }}
      role="img"
      aria-label="Cognivest"
    >
      <svg
        viewBox="0 0 64.649 75.547"
        className={styles.mark}
        style={{ height: size * 1.32 }}
        fill="currentColor"
        fillRule="evenodd"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M41.808,0.164 C30.708,3.029 21.345,7.763 17.029,17.573 C15.593,20.838 14.522,24.830 14.701,29.308 C14.955,35.673 18.341,39.945 22.509,42.595 C23.947,43.510 25.488,44.394 27.116,45.020 C32.228,46.985 38.813,47.456 45.640,47.590 C47.893,47.634 50.193,47.619 52.429,47.832 C52.580,50.105 52.575,52.400 52.575,54.718 C52.577,61.318 52.646,68.367 52.478,75.279 C48.997,75.509 45.528,75.455 42.149,75.522 C38.670,75.590 35.225,75.526 32.063,75.134 C25.810,74.359 20.719,72.490 16.351,69.751 C12.061,67.061 8.508,63.602 5.828,59.180 C3.129,54.726 0.947,49.929 0.300,43.614 C-0.050,40.187 -0.124,36.757 0.252,33.576 C0.616,30.485 1.406,27.712 2.385,25.186 C6.268,15.170 13.606,8.022 23.187,3.801 C25.665,2.710 28.244,1.785 31.091,1.134 C33.948,0.481 37.083,0.228 40.548,0.067 C40.873,0.052 41.576,-0.125 41.808,0.164 Z" />
        <path d="M64.649,23.102 C61.051,22.845 56.988,22.426 53.011,22.811 C43.984,23.685 36.645,26.976 32.595,33.092 C31.595,34.601 30.664,36.321 30.849,38.717 C31.047,41.286 32.716,42.946 34.292,44.197 C34.478,44.345 34.840,44.520 34.825,44.827 C31.244,44.619 28.204,43.591 25.562,42.306 C22.894,41.006 20.722,39.182 19.064,36.923 C17.405,34.660 16.180,31.371 16.349,27.757 C16.691,20.421 19.631,15.261 23.622,11.270 C27.606,7.286 32.635,4.486 38.752,2.638 C41.849,1.703 45.091,1.108 48.596,0.601 C48.686,0.588 49.040,0.487 49.324,0.553 C49.661,0.632 50.080,1.429 50.391,1.862 C54.049,6.961 57.450,12.288 60.962,17.428 C61.930,18.845 62.887,20.216 63.871,21.647 C64.175,22.085 64.607,22.533 64.649,23.102 Z" />
      </svg>
      {!markOnly && <span className={styles.word}>Cognivest</span>}
    </span>
  );
}
