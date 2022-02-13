import React from 'react';
import styles from '../Users.module.css';

const UserItem = (props) => {
    let isFollowed = props.isFollowed

    return (
        <div className={styles.item}>
            <img src={props.avatar} alt="Avatar" />
            <span className={styles.name}>{props.name}</span>
            <div className={isFollowed ? styles.unfollow : styles.follow}>
                {isFollowed
                ? <button onClick={() => props.unfollowAC(props.id)}>unfollow</button>
                : <button onClick={() => props.followAC(props.id)}>follow</button>
                }
            </div>
        </div>
    );
}

export { UserItem }