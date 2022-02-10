import React from 'react';
import avatar from '../Profile/images/ava.jpg';
import { FriendItem } from './FriendItem/FriendItem';
import styles from './Friends.module.css';

const Friends = (props) => {
    const friendsElements = props.friends.map(f => <FriendItem avatar={avatar} name={f.name} />);

    return (
        <div className={styles.friends}>
            { friendsElements }
        </div>
    );
}

export { Friends }