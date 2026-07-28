import { useEffect, useState } from 'react';
import { getNews, type NewsCategory, type NewsItem } from '../../api/news';
import { NEWS_FIXTURE, PORTFOLIO_FIXTURE } from '../../mocks/fixtures';
import { MultiSelectDropdown } from '../../components/MultiSelectDropdown';
import styles from './NewsPage.module.css';

type CategoryFilter = 'all' | NewsCategory;

const TICKER_OPTIONS = PORTFOLIO_FIXTURE.map((holding) => ({
  value: holding.ticker,
  label: holding.name,
  sublabel: holding.ticker,
}));

export function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>(NEWS_FIXTURE);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);

  useEffect(() => {
    getNews({
      category: category === 'all' ? undefined : category,
      tickers: selectedTickers.length > 0 ? selectedTickers : undefined,
    })
      .then(setNews)
      .catch(() => setNews(NEWS_FIXTURE));
  }, [category, selectedTickers]);

  const filtered = news.filter((item) => {
    const matchesCategory = category === 'all' || item.category === category;
    const matchesTicker = selectedTickers.length === 0 || (item.ticker && selectedTickers.includes(item.ticker));
    return matchesCategory && matchesTicker;
  });

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Market news — S&amp;P SL20</h1>
        <div className={styles.filters}>
          <div className={styles.pillGroup}>
            {(['all', 'macro', 'micro'] as CategoryFilter[]).map((value) => (
              <button
                key={value}
                type="button"
                className={category === value ? styles.pillActive : styles.pill}
                onClick={() => setCategory(value)}
              >
                {value === 'all' ? 'All' : value === 'macro' ? 'Macro' : 'Micro'}
              </button>
            ))}
          </div>
          <MultiSelectDropdown
            placeholder="All stocks"
            options={TICKER_OPTIONS}
            selected={selectedTickers}
            onChange={setSelectedTickers}
          />
        </div>
      </div>

      <div className={styles.list}>
        {filtered.map((item) => (
          <div key={item.headline} className={styles.item}>
            <div className={styles.tags}>
              {item.ticker && <span className={styles.tickerTag}>{item.ticker}</span>}
              <span className={styles.categoryTag}>
                {item.category === 'macro' ? 'Macro' : 'Micro'}
              </span>
            </div>
            <div className={styles.headline}>{item.headline}</div>
            <div className={styles.meta}>
              {item.source} · {item.timeAgo}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
