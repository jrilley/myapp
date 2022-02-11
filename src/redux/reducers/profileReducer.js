const ADD_POST = 'ADD-POST';
const UPDATE_POST_TEXT = 'UPDATE-POST-TEXT';

let initialState = {
    posts: [
        { id: 1, message: 'Happy new 2022 year', likesCount: 2022 },
        { id: 2, message: 'Hello', likesCount: 15 },
        { id: 3, message: 'My name is Anton', likesCount: 20 }
    ],
    newPostText: ''
};

const profileReducer = (state = initialState, action) => {
    switch (action.type) {
        case ADD_POST:
            if (!state.newPostText) return;

            let body = state.newPostText;
            return {
                ...state,
                posts: [...state.posts, { id: 4, message: body, likesCount: 0 }],
                newPostText: ''
            }
        case UPDATE_POST_TEXT:
            return {
                ...state,
                newPostText: action.text
            }
        default:
            return state;
    }
}

const addPostAC = () => ({ type: ADD_POST })

const updatePostTextAC = text =>
    ({ type: UPDATE_POST_TEXT, text: text })

export { profileReducer, addPostAC, updatePostTextAC }