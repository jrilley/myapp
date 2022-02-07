import React from 'react';
import { Route, Routes } from 'react-router-dom';
import './App.css';
import { DialogsContainer } from './Components/Dialogs/DialogsContainer';
import { Header } from './Components/Header/Header';
import { Navigation } from './Components/Navigation/Navigation';
import { Profile } from './Components/Profile/Profile';
import { Friends } from './Components/Friends/Friends';


const App = (props) => {
  return (
    <div className='app-wrapper'>
      <Header />
      <Navigation />
      <div className='app-wrapper-content'>
        <Routes>
          <Route index element={<Profile state={props.state.profileReducer} dispatch={props.dispatch} />} />
          <Route path='dialogs' element={<DialogsContainer state={props.state.dialogsReducer} dispatch={props.dispatch} />} />
          <Route path='friends' element={<Friends state={props.state.friendsReducer} />} />
        </Routes>
      </div>
    </div>
  );
}

export { App };