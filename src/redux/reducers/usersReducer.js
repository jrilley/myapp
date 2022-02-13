import avatar from '../../images/ava.jpg';

const FOLLOW = 'FOLLOW';
const UNFOLLOW = 'UNFOLLOW';
const SET_USERS = 'SET-USER';

let initialState = {
    users: []
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
                        isFollowed: true
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
                        isFollowed: false
                    }
                })
            }
        case SET_USERS:
            return {
                ...state,
                users: [...state.users, ...action.users]
            }
        default:
            return state;
    }
}

const followAC = (userId) => ({type: FOLLOW, userId});
const unfollowAC = (userId) => ({type: UNFOLLOW, userId});
const setUsersAC = (users) => ({type: SET_USERS, users});

export { usersReducer, followAC, unfollowAC, setUsersAC }