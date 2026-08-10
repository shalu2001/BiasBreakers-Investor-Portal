import { useEffect, useState } from 'react';
import { getPortfolio, type Holding, type PortfolioRange } from '../../api/portfolio';
import { PORTFOLIO_FIXTURE } from '../../mocks/fixtures';
import { HoldingCard } from '../../components/HoldingCard';
import { EmptyState } from '../../components/ui';
import styles from './PortfolioPage.module.css';

const RANGES: PortfolioRange[] = ['1M', '3M', '6M', '1Y'];

export function PortfolioPage() {
  const [range, setRange] = useState<PortfolioRange>('3M');
  const [holdings, setHoldings] = useState<Holding[]>(PORTFOLIO_FIXTURE);

  useEffect(() => {
    getPortfolio(range).then(setHoldings).catch(() => setHoldings(PORTFOLIO_FIXTURE));
  }, [range]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Current holdings</h1>
        <div className={styles.rangeTabs}>
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={r === range ? styles.rangeTabActive : styles.rangeTab}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <p className={styles.helperText}>
        Allocation and recent performance shown in percentage terms — prices move constantly, so
        weight is what matters here. Hover a candle for its close.
      </p>

      {holdings.length === 0 ? (
        <EmptyState
          icon="⌾"
          title="No holdings to show yet"
          message="Once your portfolio is built, your positions and their recent moves will appear here."
        />
      ) : (
        <div className={styles.grid}>
          {holdings.map((holding) => (
            <HoldingCard key={holding.ticker} holding={holding} chartHeight={280} />
          ))}
        </div>
      )}
    </div>
  );
}
