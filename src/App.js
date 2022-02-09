import React from 'react';
import { Route, Routes } from 'react-router-dom';
import './App.css';
import { DialogsContainer } from './Components/Dialogs/DialogsContainer';
import { Header } from './Components/Header/Header';
import { Navigation } from './Components/Navigation/Navigation';
import { Profile } from './Components/Profile/Profile';
import { FriendsContainer } from './Components/Friends/FriendsContainer';


const App = (props) => {
  return (
    <div className='app-wrapper'>
      <Header />
      <Navigation />
      <div className='app-wrapper-content'>
        <Routes>
          <Route index element={<Profile />} />
          <Route path='dialogs' element={<DialogsContainer />} />
          <Route path='friends' element={<FriendsContainer />} />
        </Routes>
      </div>
    </div>
  );
}

export { App };