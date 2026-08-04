import styles from './game.module.css';

// "How the numbers work" — money mechanics only (never the psychology being
// measured), available at any time from the top bar.
export function HelpModal({ onClose }: { onClose: () => void }) {
  return (
    <div className={styles.helpModal}>
      <div className={styles.helpBackdrop} onClick={onClose} />
      <div className={styles.helpCard}>
        <div className={styles.helpHead}>
          <h2>How the numbers work</h2>
          <button type="button" className={styles.helpClose} title="Close" onClick={onClose}>&times;</button>
        </div>
        <p className={styles.helpLead}>Every number on screen comes from two simple ideas.</p>

        <h3>1 · Your money lives in two pots</h3>
        <p><b>Total Equity</b> is your whole pot: the money in the stock <b>plus</b> your cash. They always add back to your total.</p>
        <p className={styles.helpEq}>money in stock&nbsp;+&nbsp;cash&nbsp;=&nbsp;Total Equity</p>

        <h3>2 · The slider sets the split</h3>
        <p>The slider is the share of your <b>current total money</b> you want in the stock — 0% = all cash, 100% = all in. The rest stays as cash.</p>
        <p className={styles.helpEq}>money in stock&nbsp;=&nbsp;slider % × Total Equity<br />cash&nbsp;=&nbsp;the rest</p>
        <p className={styles.helpEg}><b>Example:</b> with Rs.&nbsp;1,000,000 total, setting <b>37%</b> puts 37% × 1,000,000 = <b>Rs.&nbsp;370,000</b> in the stock and <b>Rs.&nbsp;630,000</b> in cash — which add back to 1,000,000.</p>

        <h3>3 · Buying &amp; selling</h3>
        <p>You never buy "37% fresh." The system moves only the <b>difference</b> between where you are and where you want to be — move the slider up and it buys the gap; move it down and it sells the gap.</p>
        <p className={styles.helpEq}>trade&nbsp;=&nbsp;(money you want in the stock) − (money you have in it now)</p>

        <h3>4 · Gains, losses &amp; the two percentages</h3>
        <p>Your Total Equity rises and falls as your stock's price moves. Two different percentages appear on screen:</p>
        <p className={styles.helpEq}><b>"since your last move"</b> → change since your <b>previous decision</b><br /><b>% beside each stock</b> → how it moved <b>today</b></p>
        <p className={styles.helpNoteText}>Percentages are always a share of your <b>current</b> total money, not your starting million — so a rising stock becomes a bigger share even if you don't trade.</p>
      </div>
    </div>
  );
}
