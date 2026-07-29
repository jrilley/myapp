import { createStore, combineReducers, applyMiddleware } from 'redux';
import thunk from 'redux-thunk';
import { profileReducer } from './reducers/profileReducer';
import { dialogsReducer } from './reducers/dialogsReducer';
import { usersReducer } from './reducers/usersReducer';
import { applicationsReducer } from './reducers/applicationsReducer';

let reducers = combineReducers({
    profileReducer,
    dialogsReducer,
    usersReducer,
    applicationsReducer
});

// Досі стор був без middleware, тому асинхронні екшени були неможливі.
// thunk потрібен для завантаження заявок з API.
let store = createStore(reducers, applyMiddleware(thunk));

window.state = store.getState();
export { store }