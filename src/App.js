import React from 'react';
import { Route, Routes } from 'react-router-dom';
import './App.css';
import { ApplicationsContainer } from './Components/Applications/ApplicationsContainer';


const App = () => {
  return (
    <div className='app-wrapper'>
      <div className='app-wrapper-content'>
        <Routes>
          {/* Заявки — єдина сторінка, тому вони і на корені.
              '/applications' лишено як аліас: на нього посилаються README
              та docs/schema.pdf. */}
          <Route index element={<ApplicationsContainer />} />
          <Route path='applications' element={<ApplicationsContainer />} />
        </Routes>
      </div>
    </div>
  );
}

export { App };
