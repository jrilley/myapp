import React from 'react';
import styles from './Friends.module.css';
import avatar from '../Profile/images/ava.jpg';
import { FriendItem } from './FriendItem/FriendItem';

const Friends = (props) => {
    const friendsElements = props.state.friends.map( f => <FriendItem avatar={avatar} name={f.name} /> );

    return (
        <div className={styles.friends}>
            { friendsElements }
        </div>
    );
}

export { Friends }