import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Provider } from 'react-redux';
import { App } from './App';
import { store } from './redux/redux-store';
import { applicationsAPI } from './api/api';

// App покладається на Router і на Redux-стор (див. index.js), тому в тестах
// його треба обгортати так само. MemoryRouter замість BrowserRouter — щоб
// задавати маршрут напряму й не чіпати history браузера.
//
// API підміняємо: сторінка ходить у мережу одразу на монтуванні, а jsdom
// реальний запит виконати не може.
jest.mock('./api/api', () => ({
    applicationsAPI: { getApplications: jest.fn() }
}));

const renderApp = (route = '/') => render(
    <MemoryRouter initialEntries={[route]}>
        <Provider store={store}>
            <App />
        </Provider>
    </MemoryRouter>
);

beforeEach(() => {
    applicationsAPI.getApplications.mockResolvedValue({
        items: [{
            id: 1,
            full_name: 'Олена Ковальчук',
            contact: 'olena@example.com',
            category: 'Співпраця',
            description: 'Опис тестової заявки',
            status: 'published',
            created_at: '2026-07-29T14:20:11'
        }],
        total: 1,
        limit: 10,
        offset: 0
    });
});

test('на кореневому маршруті одразу показує заявки', async () => {
    renderApp('/');

    expect(await screen.findByText('Заявки з Telegram')).toBeInTheDocument();
    expect(await screen.findByText('Олена Ковальчук')).toBeInTheDocument();
    expect(applicationsAPI.getApplications).toHaveBeenCalled();
});

test('/applications лишається робочим аліасом', async () => {
    renderApp('/applications');

    expect(await screen.findByText('Олена Ковальчук')).toBeInTheDocument();
});

test('показує повідомлення, якщо API недоступний', async () => {
    applicationsAPI.getApplications.mockRejectedValue(new Error('network'));

    renderApp('/');

    await waitFor(() => {
        expect(screen.getByText(/Не вдалося завантажити заявки/)).toBeInTheDocument();
    });
});
