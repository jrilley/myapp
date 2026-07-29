import React from 'react';
import { Route, Routes } from 'react-router-dom';
import './App.css';
import { DialogsContainer } from './Components/Dialogs/DialogsContainer';
import { Header } from './Components/Header/Header';
import { Navigation } from './Components/Navigation/Navigation';
import { Profile } from './Components/Profile/Profile';
import { UsersContainer } from './Components/Users/UsersContainer';
import { ApplicationsContainer } from './Components/Applications/ApplicationsContainer';


const App = (props) => {
  return (
    <div className='app-wrapper'>
      <Header />
      <Navigation />
      <div className='app-wrapper-content'>
        <Routes>
          <Route index element={<Profile />} />
          <Route path='dialogs' element={<DialogsContainer />} />
          <Route path='users' element={<UsersContainer />} />
          <Route path='applications' element={<ApplicationsContainer />} />
        </Routes>
      </div>
    </div>
  );
}

export { App };