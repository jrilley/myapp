import React, { useState, useEffect, useRef } from 'react';
import styles from './Users.module.css';
import avatar from './../Profile/images/ava.jpg';
import * as axios from 'axios';

const Users = (props) => {
    const pageSpan = useRef(null);

    useEffect(() => {
        if (props.users.length === 0) {
            axios.get(`https://social-network.samuraijs.com/api/1.0/users?count=${props.pageSize}&page=${props.currentPage}`)
                .then(response => {
                    props.setUsers(response.data.items);
                    props.setUsersTotalCount(response.data.totalCount);
                });
        }
    });

    const changeCurrentPage = () => {
        let value = pageSpan.current.innerHTML;
        // alert(value);
        props.setCurrentPage(value);
    }

    const totalPages = Math.ceil(props.totalCount / props.pageSize);
    let pages = [];

    for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
    }
    
        // pages.map(p => <span className={props.currentPage === p ? styles.currentPage : ""}>
        //  {p} </span>
        // )
    

    return (
        <div className={styles.friends}>
        <div>
            <input ref={pageSpan} type="number"></input>
            <button onClick={changeCurrentPage}>Go</button>
        </div>
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