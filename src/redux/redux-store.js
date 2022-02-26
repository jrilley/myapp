import { createStore, combineReducers } from 'redux';
import { profileReducer } from './reducers/profileReducer';
import { dialogsReducer } from './reducers/dialogsReducer';
import { usersReducer } from './reducers/usersReducer';

let reducers = combineReducers({
    profileReducer,
    dialogsReducer,
    usersReducer
});

let store = createStore(reducers);

window.state = store.getState();
export { store }