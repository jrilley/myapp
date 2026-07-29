import React, { useEffect } from 'react';
import styles from './Applications.module.css';

const Applications = (props) => {
    const { currentPage, pageSize, requestApplications } = props;

    // Масив залежностей обов'язковий: без нього запит іде на кожен рендер
    // (саме цей баг живе в Users.jsx).
    useEffect(() => {
        requestApplications(currentPage, pageSize);
    }, [currentPage, pageSize, requestApplications]);

    const totalPages = Math.ceil(props.totalCount / props.pageSize) || 1;

    // Тільки міняємо сторінку — завантаження зробить useEffect вище.
    // Якби тут теж викликався requestApplications, запит пішов би двічі.
    const goToPage = (page) => {
        if (page >= 1 && page <= totalPages) {
            props.setCurrentPage(page);
        }
    }

    return (
        <div className={styles.applications}>
            <h2>Заявки з Telegram</h2>

            {props.error && <div className={styles.error}>{props.error}</div>}
            {props.isFetching && <div className={styles.loading}>Завантаження…</div>}

            {!props.isFetching && !props.error && props.applications.length === 0 &&
                <div className={styles.empty}>Заявок поки немає.</div>
            }

            {props.applications.map(a =>
                <div key={a.id} className={styles.item}>
                    <div className={styles.head}>
                        <span className={styles.category}>{a.category}</span>
                        <span className={styles.date}>
                            {new Date(a.created_at).toLocaleString()}
                        </span>
                    </div>
                    <div className={styles.name}>{a.full_name}</div>
                    <div className={styles.description}>{a.description}</div>
                </div>
            )}

            {totalPages > 1 &&
                <div className={styles.pagination}>
                    <button
                        onClick={() => goToPage(props.currentPage - 1)}
                        disabled={props.currentPage <= 1}
                    >Назад</button>
                    <span className={styles.pageInfo}>
                        {props.currentPage} / {totalPages}
                    </span>
                    <button
                        onClick={() => goToPage(props.currentPage + 1)}
                        disabled={props.currentPage >= totalPages}
                    >Далі</button>
                </div>
            }
        </div>
    );
}

export { Applications }
