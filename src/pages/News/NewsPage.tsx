import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { getNews, type NewsCategory, type NewsItem } from '../../api/news';
import { EmptyState } from '../../components/ui';
import { formatTimeAgo } from '../../utils/timeAgo';
import styles from './NewsPage.module.css';

type CategoryFilter = 'all' | NewsCategory;

const PAGE_SIZE = 8;

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
  const [news, setNews] = useState<NewsItem[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [page, setPage] = useState(1);

  // Fetch the news window exactly once, on initial mount. No mock fallback:
  // the feed always reflects the endpoint (loading/error states cover the rest).
  useEffect(() => {
    getNews()
      .then((items) => {
        setNews(items);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }, []);

  const filtered = useMemo(
    () => news.filter((item) => category === 'all' || item.category === category),
    [news, category],
  );

  // any change to the filter set (or the data) sends us back to page one
  useEffect(() => {
    setPage(1);
  }, [category, news]);

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
            {status === 'loading' ? (
              <EmptyState icon="◷" title="Loading market news…" message="Fetching the latest stories." />
            ) : status === 'error' ? (
              <EmptyState
                icon="⚠"
                title="Couldn’t load market news"
                message="The news service is unavailable right now. Please try again shortly."
              />
            ) : news.length === 0 ? (
              <EmptyState icon="◷" title="No stories available" message="There’s no news for the current window." />
            ) : (
              <EmptyState
                icon="◷"
                title="No stories in this category"
                message="Try a different category."
              />
            )}
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
