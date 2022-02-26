const FOLLOW = 'FOLLOW';
const UNFOLLOW = 'UNFOLLOW';
const SET_USERS = 'SET-USER';
const SET_USERS_TOTAL_COUNT = 'SET-USERS-TOTAL-COUNT';
const SET_CURRENT_PAGE = 'SET-CURRENT-PAGE';

let initialState = {
    users: [],
    totalCount: 19,
    pageSize: 5,
    currentPage: 1
};

const usersReducer = (state = initialState, action) => {
    switch(action.type) {
        case FOLLOW:
            return {
                ...state,
                users: state.users.map(u => {
                    if (u.id !== action.userId) return u;

                    return {
                        ...u,
                        followed: true
                    }
                })
            }
        case UNFOLLOW:
            return {
                ...state,
                users: state.users.map(u => {
                    if (u.id !== action.userId) return u;

                    return {
                        ...u,
                        followed: false
                    }
                })
            }
        case SET_USERS:
            return {
                ...state,
                users: [...state.users, ...action.users]
            }
        case SET_USERS_TOTAL_COUNT:
            return {
                ...state,
                totalCount: action.totalCount
            }
        case SET_CURRENT_PAGE:
            return {
                ...state,
                currentPage: action.currentPage
            }
        default:
            return state;
    }
}

const followAC = (userId) => ({type: FOLLOW, userId});
const unfollowAC = (userId) => ({type: UNFOLLOW, userId});
const setUsersAC = (users) => ({type: SET_USERS, users});
const setUsersTotalCountAC = (totalCount) => ({type: SET_USERS_TOTAL_COUNT, totalCount})
const setCurrentPageAC = (currentPage) => ({type: SET_CURRENT_PAGE, currentPage});

export { usersReducer, followAC, unfollowAC, setUsersAC, setUsersTotalCountAC, setCurrentPageAC }