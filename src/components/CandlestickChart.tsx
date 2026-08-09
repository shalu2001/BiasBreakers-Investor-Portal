import { useEffect, useRef } from 'react';
import { createChart, CandlestickSeries, type IChartApi, type Time } from 'lightweight-charts';
import { colors } from '../theme/colors';
import type { Candle } from '../api/portfolio';

interface CandlestickChartProps {
  candles: Candle[];
  height?: number;
  /** Show dates as month/day only (no year). Used by the game so the hidden
   *  scenario's real year never shows, while the axis still reads as dates. */
  hideYear?: boolean;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Format a lightweight-charts Time as "Mmm D" (no year). Time may be a
// BusinessDay object, a 'yyyy-mm-dd' string, or a UTC timestamp (seconds).
function monthDay(time: Time): string {
  let m = 1;
  let d = 1;
  if (typeof time === 'object' && time !== null && 'day' in time) {
    m = time.month;
    d = time.day;
  } else if (typeof time === 'string') {
    const p = time.split('-');
    m = Number(p[1]);
    d = Number(p[2]);
  } else if (typeof time === 'number') {
    const dt = new Date(time * 1000);
    m = dt.getUTCMonth() + 1;
    d = dt.getUTCDate();
  }
  return `${MONTHS[m - 1] ?? ''} ${d}`;
}

export function CandlestickChart({ candles, height = 240, hideYear = false }: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      height,
      autoSize: false,
      layout: { background: { color: 'transparent' }, textColor: colors.textMuted },
      grid: {
        vertLines: { color: colors.border },
        horzLines: { color: colors.border },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: {
        borderColor: colors.border,
        ...(hideYear ? { tickMarkFormatter: (t: Time) => monthDay(t) } : {}),
      },
      ...(hideYear ? { localization: { timeFormatter: (t: Time) => monthDay(t) } } : {}),
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: colors.success,
      downColor: colors.danger,
      borderVisible: false,
      wickUpColor: colors.success,
      wickDownColor: colors.danger,
    });
    series.setData(candles);
    chart.timeScale().fitContent();

    const handleResize = () => chart.applyOptions({ width: container.clientWidth });
    handleResize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [candles, height, hideYear]);

  return <div ref={containerRef} style={{ width: '100%' }} />;
}
