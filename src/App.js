import { Route, Routes } from 'react-router-dom';
import './App.css';
import { Dialogs } from './Components/Dialogs/Dialogs';
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
          <Route index element={<Profile state={props.state.profilePage} addPost={props.addPost} />} />
          <Route path='dialogs' element={<Dialogs state={props.state.dialogPage} addMessage={props.addMessage} />} />
          <Route path='friends' element={<Friends state={props.state.friendsPage} />} />
        </Routes>
      </div>
    </div>
  );
}

export { App };