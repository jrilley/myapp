import { createStore, combineReducers } from 'redux';
import { profileReducer } from './reducers/profileReducer';
import { dialogsReducer } from './reducers/dialogsReducer';
import { friendsReducer } from './reducers/friendsReducer';

let reducers = combineReducers({
    profileReducer,
    dialogsReducer,
    friendsReducer
});

let store = createStore(reducers);

export { store }