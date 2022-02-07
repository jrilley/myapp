import React from 'react';
import { addMessageAC, updateMessageTextAC } from '../../redux/reducers/dialogsReducer';
import { Dialogs } from './Dialogs';

const DialogsContainer = (props) => {
  const addMessage = () => {
    props.dispatch(addMessageAC());
  }

  const updateNewMessageText = (text) => {
    let action = updateMessageTextAC(text)
    props.dispatch(action);
  }

  return (
    <Dialogs addMessage={addMessage}
            updateNewMessageText={updateNewMessageText}
            dialogs={props.state.dialogs}
            messages={props.state.messages}
            newMessageText={props.state.newMessageText}
            />
  );
}

export { DialogsContainer };