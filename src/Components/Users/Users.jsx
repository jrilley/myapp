import React from 'react';
import styles from './Users.module.css';

const Users = (props) => {
    return (
        <div className={styles.friends}>
            {
                props.users.map(u => <div className={styles.item}>
                    <img src={u.avatar} alt="Avatar" />
                    <span className={styles.name}>{u.name}</span>
                    <div className={u.isFollowed ? styles.unfollow : styles.follow}>
                        {u.isFollowed
                            ? <button onClick={() => props.unfollow(u.id)}>unfollow</button>
                            : <button onClick={() => props.follow(u.id)}>follow</button>
                        }
                    </div>
                </div>)
            }
        </div>
    );
}

export { Users }