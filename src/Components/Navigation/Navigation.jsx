import React from 'react';
import { NavLink } from 'react-router-dom';
import styles from './Navigation.module.css';

const setActive = ({isActive}) => isActive ? styles.activeLink : " ";

const Navigation = () => {
    return (
       <nav className={styles.nav_menu}>
        <ul>
          <li>
            <NavLink
              to="/"
              className={setActive}
            >Profile</NavLink>
          </li>
          <li>
            <NavLink
              to="/dialogs"
              className={setActive}
              >Messages</NavLink>
          </li>
          <li><NavLink
                to="/friends"
                className={setActive}
          >Friends</NavLink></li>
          <li><a href="#s">Settings</a></li>
        </ul>
      </nav>
    );
}

export { Navigation };