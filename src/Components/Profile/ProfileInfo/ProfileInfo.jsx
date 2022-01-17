import styles from './ProfileInfo.module.css';
import avatar from '../images/ava.jpg';
import coverImg from '../images/cover.jpg';

const ProfileInfo = (props) => {
    return (
        <>
            <div className={styles.cover_image}>
                <img src={coverImg} alt="cover" />
            </div>
            <div className={styles.content}>
                <div className={styles.avatar}><img src={avatar} alt="profilePhoto" /></div>
                <div className={styles.description}>
                    <p><strong>Name</strong>: Anton</p>
                    <p><strong>Country</strong>: Ukraine</p>
                    <p><strong>Age</strong>: 20</p>
                </div>
            </div>
        </>
    );
}

export { ProfileInfo };