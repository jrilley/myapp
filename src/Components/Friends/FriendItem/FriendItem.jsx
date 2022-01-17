import styles from '../Friends.module.css';

const FriendItem = (props) => {
    return (
        <div className={styles.item}>
            <img src={props.avatar} alt="Avatar" />
            <span className={styles.name}>{props.name}</span>
            <div className={styles.follow}>
                <button>Follow</button>
            </div>
        </div>
    );
}

export { FriendItem }