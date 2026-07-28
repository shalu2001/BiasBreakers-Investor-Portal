import { CandlestickChart } from './CandlestickChart';
import type { Holding } from '../api/portfolio';
import styles from './HoldingCard.module.css';

interface HoldingCardProps {
  holding: Holding;
  dateRangeLabel?: string;
  footerNote?: string;
  chartHeight?: number;
}

export function HoldingCard({ holding, dateRangeLabel, footerNote, chartHeight }: HoldingCardProps) {
  const isPositive = holding.changePct >= 0;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <div>
          <div className={styles.ticker}>{holding.ticker}</div>
          <div className={styles.name}>{holding.name}</div>
        </div>
        <div className={isPositive ? styles.changePositive : styles.changeNegative}>
          {isPositive ? '+' : ''}
          {holding.changePct.toFixed(1)}%
        </div>
      </div>
      {dateRangeLabel && <div className={styles.dateRange}>{dateRangeLabel}</div>}

      <CandlestickChart candles={holding.candles} height={chartHeight} />

      <div className={styles.footer}>
        {holding.sector} · {holding.weightPct}% of portfolio
        {footerNote ? ` · ${footerNote}` : ''}
      </div>
    </div>
  );
}
