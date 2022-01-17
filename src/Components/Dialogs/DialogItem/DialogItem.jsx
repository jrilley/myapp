import { NavLink } from 'react-router-dom';
import styles from './DialogItem.module.css';

const DialogItem = (props) => {
    return (
        <li className={styles.dialogItem}>
            <NavLink to={'/dialogs/' + props.id}>{props.name}</NavLink>
        </li>
    );
}

export { DialogItem };