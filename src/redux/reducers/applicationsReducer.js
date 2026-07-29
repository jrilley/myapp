import { applicationsAPI } from '../../api/api';

const SET_APPLICATIONS = 'SET-APPLICATIONS';
const SET_TOTAL_COUNT = 'SET-APPLICATIONS-TOTAL-COUNT';
const SET_CURRENT_PAGE = 'SET-APPLICATIONS-CURRENT-PAGE';
const TOGGLE_IS_FETCHING = 'TOGGLE-APPLICATIONS-IS-FETCHING';
const SET_ERROR = 'SET-APPLICATIONS-ERROR';

let initialState = {
    applications: [],
    totalCount: 0,
    pageSize: 10,
    currentPage: 1,
    isFetching: false,
    error: null
};

const applicationsReducer = (state = initialState, action) => {
    switch (action.type) {
        case SET_APPLICATIONS:
            return {
                ...state,
                applications: action.applications
            }
        case SET_TOTAL_COUNT:
            return {
                ...state,
                totalCount: action.totalCount
            }
        case SET_CURRENT_PAGE:
            return {
                ...state,
                currentPage: action.currentPage
            }
        case TOGGLE_IS_FETCHING:
            return {
                ...state,
                isFetching: action.isFetching
            }
        case SET_ERROR:
            return {
                ...state,
                error: action.error
            }
        default:
            return state;
    }
}

const setApplicationsAC = (applications) => ({ type: SET_APPLICATIONS, applications });
const setTotalCountAC = (totalCount) => ({ type: SET_TOTAL_COUNT, totalCount });
const setCurrentPageAC = (currentPage) => ({ type: SET_CURRENT_PAGE, currentPage });
const toggleIsFetchingAC = (isFetching) => ({ type: TOGGLE_IS_FETCHING, isFetching });
const setErrorAC = (error) => ({ type: SET_ERROR, error });

// Thunk: у сторі досі не було middleware, тому асинхронність з'явилась саме тут.
const requestApplications = (page, pageSize) => async (dispatch) => {
    dispatch(toggleIsFetchingAC(true));
    dispatch(setErrorAC(null));
    try {
        const data = await applicationsAPI.getApplications(pageSize, (page - 1) * pageSize);
        dispatch(setApplicationsAC(data.items));
        dispatch(setTotalCountAC(data.total));
        dispatch(setCurrentPageAC(page));
    } catch (e) {
        dispatch(setErrorAC('Не вдалося завантажити заявки. Перевірте, чи запущено API.'));
    } finally {
        dispatch(toggleIsFetchingAC(false));
    }
}

export {
    applicationsReducer,
    setApplicationsAC,
    setTotalCountAC,
    setCurrentPageAC,
    toggleIsFetchingAC,
    setErrorAC,
    requestApplications
}
