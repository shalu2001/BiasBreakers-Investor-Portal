import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { getNews, getTickers, type NewsCategory, type NewsItem, type TickerOption } from '../../api/news';
import { NEWS_FIXTURE, PORTFOLIO_FIXTURE } from '../../mocks/fixtures';
import { MultiSelectDropdown } from '../../components/MultiSelectDropdown';
import { EmptyState } from '../../components/ui';
import { formatTimeAgo } from '../../utils/timeAgo';
import styles from './NewsPage.module.css';

type CategoryFilter = 'all' | NewsCategory;

const PAGE_SIZE = 8;

const FALLBACK_TICKER_OPTIONS: TickerOption[] = PORTFOLIO_FIXTURE.map((holding) => ({
  ticker: holding.ticker,
  name: holding.name,
}));

function snippet(text: string, max = 180): string {
  if (!text || text.length <= max) return text;
  return text.slice(0, max).replace(/\s+\S*$/, '') + '…';
}

// compact page list: 1 … 4 5 [6] 7 8 … 20
function windowedPages(current: number, total: number): (number | 'gap')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | 'gap')[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) pages.push('gap');
  for (let p = start; p <= end; p++) pages.push(p);
  if (end < total - 1) pages.push('gap');
  pages.push(total);
  return pages;
}

export function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>(NEWS_FIXTURE);
  const [tickerOptions, setTickerOptions] = useState<TickerOption[]>(FALLBACK_TICKER_OPTIONS);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);
  const [page, setPage] = useState(1);

  useEffect(() => {
    getNews().then(setNews).catch(() => setNews(NEWS_FIXTURE));
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

  const filtered = useMemo(
    () =>
      news.filter((item) => {
        const matchesCategory = category === 'all' || item.category === category;
        const matchesTicker =
          selectedTickers.length === 0 || (item.ticker && selectedTickers.includes(item.ticker));
        return matchesCategory && matchesTicker;
      }),
    [news, category, selectedTickers],
  );

  // any change to the filter set (or the data) sends us back to page one
  useEffect(() => {
    setPage(1);
  }, [category, selectedTickers, news]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pageCount);
  const paged = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);

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

      <div className={styles.resultMeta}>
        {filtered.length} {filtered.length === 1 ? 'story' : 'stories'}
      </div>

      <div className={styles.list}>
        {paged.map((item, index) => (
          <Link
            key={`${item.headline}-${index}`}
            to="/news/article"
            state={{ article: item }}
            className={styles.item}
          >
            <div className={styles.tags}>
              {item.ticker && <span className={styles.tickerTag}>{item.ticker}</span>}
              <span className={styles.categoryTag}>{item.category === 'macro' ? 'Macro' : 'Micro'}</span>
            </div>
            <div className={styles.headline}>{item.headline}</div>
            {item.content && <p className={styles.content}>{snippet(item.content)}</p>}
            <div className={styles.itemFooter}>
              <span className={styles.meta}>
                {item.source}
                {item.source ? ' · ' : ''}
                {formatTimeAgo(item.publishedDate)}
              </span>
              <span className={styles.readMore}>Read full story →</span>
            </div>
          </Link>
        ))}
        {paged.length === 0 && (
          <div className={styles.empty}>
            <EmptyState
              icon="◷"
              title="No stories match these filters"
              message="Try switching category or clearing the stock filter."
            />
          </div>
        )}
      </div>

      {pageCount > 1 && (
        <div className={styles.pagination}>
          <button
            type="button"
            className={styles.pageBtn}
            disabled={current === 1}
            onClick={() => setPage(current - 1)}
          >
            ‹ Prev
          </button>
          {windowedPages(current, pageCount).map((p, i) =>
            p === 'gap' ? (
              <span key={`gap-${i}`} className={styles.ellipsis}>…</span>
            ) : (
              <button
                key={p}
                type="button"
                className={p === current ? styles.pageNumActive : styles.pageNum}
                onClick={() => setPage(p)}
              >
                {p}
              </button>
            ),
          )}
          <button
            type="button"
            className={styles.pageBtn}
            disabled={current === pageCount}
            onClick={() => setPage(current + 1)}
          >
            Next ›
          </button>
        </div>
      )}
    </div>
  );
}
