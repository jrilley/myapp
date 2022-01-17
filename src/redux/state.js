import { rerenderEntireTree } from "../render";

const state = {
    profilePage: {
        posts: [
            { id: 1, message: 'Happy new 2022 year', likesCount: 2022 },
            { id: 1, message: 'Hello', likesCount: 15 },
            { id: 1, message: 'My name is Anton', likesCount: 20 }
        ]
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
        ]
    },
    friendsPage: {
        friends: [
            {id: 2, name: 'Roman'},
            {id: 3, name: 'Alex'}
        ]
    }
};

const addPost = (msg) => {
    const post = {
        id: 5,
        message: msg,
        likesCount: 0
    };

    state.profilePage.posts.push(post);
    rerenderEntireTree(state);
}

const addMessage = (msg) => {
    const message = {
        id: 5,
        message: msg
    };

    state.dialogPage.messages.push(message);
    rerenderEntireTree(state);
}

export { state, addPost, addMessage }