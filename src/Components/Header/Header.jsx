import React from 'react';
import { NavLink } from 'react-router-dom';
import logo from '../../reactLogo.png';
import styles from './Header.module.css';

const Header = () => {
  return (
    <header className={styles.header}>
      <div className={styles.header_logo}>
        <NavLink to="/">
          <img src={logo} alt='headerLogo' />
        </NavLink>
      </div>
      <div className={styles.header_search}>
        <span>Search</span>
      </div>
    </header>
  );
}

export { Header };