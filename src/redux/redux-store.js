import { createStore, combineReducers, applyMiddleware } from 'redux';
import thunk from 'redux-thunk';
import { applicationsReducer } from './reducers/applicationsReducer';

let reducers = combineReducers({
    applicationsReducer
});

// thunk потрібен для завантаження заявок з API — синхронний стор
// асинхронних екшенів не приймає.
let store = createStore(reducers, applyMiddleware(thunk));

export { store }
