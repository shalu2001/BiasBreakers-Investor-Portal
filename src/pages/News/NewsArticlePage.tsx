import { Link, useLocation } from 'react-router-dom';
import type { NewsItem } from '../../api/news';
import { formatTimeAgo } from '../../utils/timeAgo';
import styles from './NewsArticlePage.module.css';

// Full-story view. The article is handed over via router state when the user
// clicks a card on the news list, so no extra fetch or article-id scheme is
// needed. Opened directly (e.g. a refresh) there's no state, so we fall back to
// a gentle "open it from the list" message.
export function NewsArticlePage() {
  const location = useLocation();
  const article = (location.state as { article?: NewsItem } | null)?.article ?? null;

  if (!article) {
    return (
      <div className={styles.page}>
        <Link to="/news" className={styles.back}>← Back to news</Link>
        <p className={styles.missing}>This story isn’t available directly — please open it from the news list.</p>
      </div>
    );
  }

  const paragraphs = article.content.split(/\n{2,}|\r?\n/).filter((p) => p.trim().length > 0);

  return (
    <div className={styles.page}>
      <Link to="/news" className={styles.back}>← Back to news</Link>
      <article className={styles.article}>
        <div className={styles.tags}>
          {article.ticker && <span className={styles.tickerTag}>{article.ticker}</span>}
          <span className={styles.categoryTag}>{article.category === 'macro' ? 'Macro' : 'Micro'}</span>
        </div>
        <h1 className={styles.headline}>{article.headline}</h1>
        <div className={styles.meta}>
          {article.source}
          {article.source ? ' · ' : ''}
          {formatTimeAgo(article.publishedDate)}
        </div>
        <div className={styles.body}>
          {paragraphs.length > 0
            ? paragraphs.map((para, i) => <p key={i}>{para}</p>)
            : <p>{article.content}</p>}
        </div>
      </article>
    </div>
  );
}
