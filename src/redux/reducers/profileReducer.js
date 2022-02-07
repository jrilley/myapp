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
    switch(action.type) {
        case ADD_POST:
            if (!state.newPostText) {
                return;
            }

            const post = {
                id: 5,
                message: state.newPostText,
                likesCount: 0
            };
        
            state.posts.push(post);
            state.newPostText = '';
            return state;
        case UPDATE_POST_TEXT:
            state.newPostText = action.text;
            return state;
        default:
            return state;
    }
}

const addPostAC = () => ({ type: ADD_POST })

const updatePostTextAC = text =>
    ({ type: UPDATE_POST_TEXT, text: text })

export { profileReducer, addPostAC, updatePostTextAC }