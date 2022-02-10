const ADD_MESSAGE = 'ADD-MESSAGE';
const UPDATE_MESSAGE_TEXT = 'UPDATE-MESSAGE-TEXT';

let initialState = {
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
};

const dialogsReducer = (state = initialState, action) => {
    switch(action.type) {
        case ADD_MESSAGE: {
            if (!state.newMessageText) {
                return;
            }
            const message = {
                id: 5,
                message: state.newMessageText
            };

            let stateCopy = {...state};
            stateCopy.messages = [...state.messages]   
            stateCopy.messages.push(message);
            stateCopy.newMessageText = '';
            return stateCopy;
        }
        case UPDATE_MESSAGE_TEXT: {
            let stateCopy = {...state}
            stateCopy.newMessageText = action.text;
            return stateCopy;
        }
        default:
            return state;
    }
}

const addMessageAC = () => {
    return {
        type: ADD_MESSAGE
    }
}

const updateMessageTextAC = text => {
    return {
        type: UPDATE_MESSAGE_TEXT,
        text: text
    }
}

export { dialogsReducer, addMessageAC, updateMessageTextAC }