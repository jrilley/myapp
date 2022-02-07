import React from 'react';
import styles from './Post.module.css';
import avatar from '../../images/ava.jpg';

const Post = (props) => {
    return (
        <div className={styles.posts}>
            <div className={styles.item}>
                <img src={avatar} alt="Avatar" />
                <span className={styles.message}>{props.message}</span>
                <div className={styles.likes}>
                    <span>{props.likesCount} likes</span>
                    <hr />
                    <button>like</button>
                </div>
            </div>
        </div>
    );
}

export default Post;