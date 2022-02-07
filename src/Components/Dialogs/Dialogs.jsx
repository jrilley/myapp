import React from 'react';
import { DialogItem } from './DialogItem/DialogItem';
import { MessageItem } from './MessageItem/MessageItem';
import styles from './Dialogs.module.css';
import { addMessageAC, updateMessageTextAC } from '../../redux/reducers/dialogsReducer';

const Dialogs = (props) => {
  const dialogsElements = props.state.dialogs.map( dialog => <DialogItem name={dialog.name} id={dialog.id} /> )
  const messagesElements = props.state.messages.map( msg => <MessageItem message={msg.message} /> )

  const messageText = React.createRef();

  const addMessage = () => {
    props.dispatch(addMessageAC());
  }

  const updateNewMessageText = () => {
    const text = messageText.current.value;

    props.dispatch(updateMessageTextAC(text));
  }

  return (
    <div className={styles.dialogs}>
      <div className={styles.dialog}>
        <ul>
          { dialogsElements }
        </ul>
      </div>
      <div className={styles.messages}>
        <div className={styles.messageItems}>
          {messagesElements}
        </div>
        <div className={styles.sendMessage}>
          <textarea onChange={updateNewMessageText}
                    ref={messageText}
                    value={props.state.newMessageText}/>
          <button onClick={ addMessage }>Send message</button>
        </div>
      </div>
    </div>
  );
}

export { Dialogs };