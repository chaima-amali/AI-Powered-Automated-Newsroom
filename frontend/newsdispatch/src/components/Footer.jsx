import styles from './Footer.module.css';

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <div className={styles.brand}>
          <div className={styles.logoRow}>
            <div className={styles.logoMark}>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M1 3h10M1 6h7M1 9h8" stroke="white" strokeWidth="1.4" strokeLinecap="round"/>
              </svg>
            </div>
            <span className={styles.logoText}>News Dispatch</span>
          </div>
          <p className={styles.tagline}>The world's stories, curated for you.</p>
          <p className={styles.address}>123 Pennsylvania St. Suite 200<br />New York City</p>
        </div>

        <div className={styles.cols}>
          <div className={styles.col}>
            <h4>Company</h4>
            <a href="#">About</a>
            <a href="#">Careers</a>
            <a href="#">Press</a>
            <a href="#">Contact</a>
          </div>
          <div className={styles.col}>
            <h4>Product</h4>
            <a href="#">Features</a>
            <a href="#">Pricing</a>
            <a href="#">API</a>
            <a href="#">Mobile App</a>
          </div>
          <div className={styles.col}>
            <h4>Legal</h4>
            <a href="#">Privacy</a>
            <a href="#">Terms</a>
            <a href="#">Cookies</a>
          </div>
        </div>
      </div>

      <div className={styles.bottom}>
        <div className={styles.bottomLeft}>
          <span>© 2024 News Dispatch. All rights reserved.</span>
        </div>
        <span className={styles.bottomRight}>info@newsdispatch.com</span>
      </div>
    </footer>
  );
}
