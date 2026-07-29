import * as axios from 'axios';

// У dev працює через "proxy" у package.json, тому за замовчуванням відносний шлях.
// Для продакшн-збірки задайте REACT_APP_API_URL.
// УВАГА: усе з префіксом REACT_APP_ вшивається у публічний бандл,
// тому сюди можна класти лише URL — ніколи токен бота чи ADMIN_API_TOKEN.
const instance = axios.create({
    baseURL: process.env.REACT_APP_API_URL || '/api'
});

const applicationsAPI = {
    getApplications(limit = 20, offset = 0) {
        return instance.get(`applications?limit=${limit}&offset=${offset}`)
            .then(response => response.data);
    }
};

export { instance, applicationsAPI }
