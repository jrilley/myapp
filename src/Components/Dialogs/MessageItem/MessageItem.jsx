import React from 'react';
import styles from './MessageItem.module.css';

const MessageItem = (props) => {
    return (
        <p className={styles.messageItem}>{props.message}</p>
    );
}

export { MessageItem };