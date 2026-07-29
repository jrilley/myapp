import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Provider } from 'react-redux';
import { App } from './App';
import { store } from './redux/redux-store';

// App покладається на Router і на Redux-стор (див. index.js), тому в тестах
// його треба обгортати так само. MemoryRouter замість BrowserRouter — щоб
// задавати маршрут напряму й не чіпати history браузера.
const renderApp = (route = '/') => render(
    <MemoryRouter initialEntries={[route]}>
        <Provider store={store}>
            <App />
        </Provider>
    </MemoryRouter>
);

test('рендерить навігаційне меню', () => {
    renderApp();

    expect(screen.getByRole('link', { name: 'Profile' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Messages' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Заявки' })).toBeInTheDocument();
});

test('на кореневому маршруті показує профіль', () => {
    renderApp('/');

    // "Ukraine" є лише в ProfileInfo; "Anton" не годиться — це слово
    // трапляється ще й у тексті поста з profileReducer.
    expect(screen.getByText(/Ukraine/)).toBeInTheDocument();
});
