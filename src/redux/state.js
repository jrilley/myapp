import { profileReducer } from './reducers/profileReducer';
import { dialogsReducer } from './reducers/dialogsReducer';

let store = {
    _rerenderEntireTree() {
        console.log('no subscribers');
    },

    _state: {
        profilePage: {
            posts: [
                { id: 1, message: 'Happy new 2022 year', likesCount: 2022 },
                { id: 1, message: 'Hello', likesCount: 15 },
                { id: 1, message: 'My name is Anton', likesCount: 20 }
            ],
            newPostText: ''
        },
        dialogPage: {
            messages: [
                { id: 1, message: 'Hello' },
                { id: 2, message: 'How are u' },
                { id: 3, message: 'Ho ho ho' },
                { id: 4, message: '2022' }
            ],
            dialogs: [
                { id: 1, name: 'Anton' },
                { id: 2, name: 'Roman' },
                { id: 3, name: 'Alex' }
            ],
            newMessageText: ''
        },
        friendsPage: {
            friends: [
                {id: 2, name: 'Roman'},
                {id: 3, name: 'Alex'}
            ]
        }
    },

    getState() {
        return this._state;
    },

    subscribe(observer) {
        this._rerenderEntireTree = observer;
    },

    dispatch(action) {
        this._state.profilePage = profileReducer(this._state.profilePage, action);
        this._state.dialogPage = dialogsReducer(this._state.dialogPage, action);

        this._rerenderEntireTree();
    }
}

export { store }

window.state = store.getState();
window.store = store;