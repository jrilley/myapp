import React from 'react';
import ReactDOM from 'react-dom';
import './index.css';
import { App } from './App';
import { BrowserRouter } from 'react-router-dom';
import { addPost, addMessage } from './redux/state';

const rerenderEntireTree = (state) => {
  ReactDOM.render(
    <React.StrictMode>
      <BrowserRouter>
        <App state={state} addPost={addPost} addMessage={addMessage} />
      </BrowserRouter>
    </React.StrictMode>,
    document.getElementById('root')
  );
}

export { rerenderEntireTree };