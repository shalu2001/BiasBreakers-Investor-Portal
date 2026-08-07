import { useEffect, useMemo, useState } from 'react';
import { getNews, getTickers, type NewsCategory, type NewsItem, type TickerOption } from '../../api/news';
import { NEWS_FIXTURE, PORTFOLIO_FIXTURE } from '../../mocks/fixtures';
import { MultiSelectDropdown } from '../../components/MultiSelectDropdown';
import { formatTimeAgo } from '../../utils/timeAgo';
import styles from './NewsPage.module.css';

type CategoryFilter = 'all' | NewsCategory;

const FALLBACK_TICKER_OPTIONS: TickerOption[] = PORTFOLIO_FIXTURE.map((holding) => ({
  ticker: holding.ticker,
  name: holding.name,
}));

export function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>(NEWS_FIXTURE);
  const [tickerOptions, setTickerOptions] = useState<TickerOption[]>(FALLBACK_TICKER_OPTIONS);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);

  useEffect(() => {
    getNews()
      .then(setNews)
      .catch(() => setNews(NEWS_FIXTURE));
  }, []);

  useEffect(() => {
    getTickers()
      .then((options) => setTickerOptions(options.length > 0 ? options : FALLBACK_TICKER_OPTIONS))
      .catch(() => setTickerOptions(FALLBACK_TICKER_OPTIONS));
  }, []);

  const dropdownOptions = useMemo(
    () => tickerOptions.map((option) => ({ value: option.ticker, label: option.name, sublabel: option.ticker })),
    [tickerOptions],
  );

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
            options={dropdownOptions}
            selected={selectedTickers}
            onChange={setSelectedTickers}
          />
        </div>
      </div>

      <div className={styles.list}>
        {filtered.map((item, index) => (
          <div key={`${item.headline}-${index}`} className={styles.item}>
            <div className={styles.tags}>
              {item.ticker && <span className={styles.tickerTag}>{item.ticker}</span>}
              <span className={styles.categoryTag}>
                {item.category === 'macro' ? 'Macro' : 'Micro'}
              </span>
            </div>
            <div className={styles.headline}>{item.headline}</div>
            {item.content && <div className={styles.content}>{item.content}</div>}
            <div className={styles.meta}>
              {item.source} · {formatTimeAgo(item.publishedDate)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
