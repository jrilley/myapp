import avatar from '../../images/ava.jpg';

const FOLLOW = 'FOLLOW';
const UNFOLLOW = 'UNFOLLOW';

let initialState = {
    users: [
        {id: 2, name: 'Roman', avatar: avatar, isFollowed: false},
        {id: 3, name: 'Alex', avatar: avatar, isFollowed: true}
    ]
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
        default:
            return state;
    }
}

const followAC = (userId) => ({type: FOLLOW, userId});
const unfollowAC = (userId) => ({type: UNFOLLOW, userId});

export { usersReducer, followAC, unfollowAC }