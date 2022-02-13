import React from 'react';
import styles from './Users.module.css';
import avatar from './../Profile/images/ava.jpg';
import * as axios from 'axios';

const Users = (props) => {

    let getUsers = () => {
        if (props.users.length === 0) {
            axios.get('https://social-network.samuraijs.com/api/1.0/users')
            .then(response => {
                debugger;
                props.setUsers(response.data.items);
            });
        }
    }
    
    return (
        <div className={styles.friends}>
        <button onClick={getUsers}>Get users</button>
            {
                props.users.map(u => <div className={styles.item}>
                    {
                        u.photos.small
                            ? <img src={u.photos.small} alt="Avatar" />
                            : <img src={avatar} alt="Avatar" />
                    }
                    <span className={styles.name}>{u.name}</span>
                    <div className={u.followed ? styles.unfollow : styles.follow}>
                        {u.followed
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