import React from 'react';
import { addMessageAC, updateMessageTextAC } from '../../redux/reducers/dialogsReducer';
import { StoreContext } from '../../StoreContext';
import { Dialogs } from './Dialogs';

const DialogsContainer = (props) => {
  return (
    <StoreContext.Consumer>
      {
        (store) => {
          let state = store.getState();

          const addMessage = () => {
            store.dispatch(addMessageAC());
          }

          const updateNewMessageText = (text) => {
            let action = updateMessageTextAC(text)
            store.dispatch(action);
          }

          return <Dialogs addMessage={addMessage}
            updateNewMessageText={updateNewMessageText}
            dialogs={state.dialogsReducer.dialogs}
            messages={state.dialogsReducer.messages}
            newMessageText={state.dialogsReducer.newMessageText}
          />
        }
      }
    </StoreContext.Consumer>
  );
}

export { DialogsContainer };