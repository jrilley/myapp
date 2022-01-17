import logo from '../../logo.svg';
import styles from './Header.module.css';

const Header = () => {
    return (
      <header className={styles.header}>
        <div className={styles.header_logo}>
          <a href="#s"><img src={logo} alt='headerLogo' /></a>
        </div>
        <div className={styles.header_search}>
          <span>Search</span>
        </div>
      </header>
    );
}

export { Header };