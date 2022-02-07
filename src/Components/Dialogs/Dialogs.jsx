import React from 'react';
import { DialogItem } from './DialogItem/DialogItem';
import { MessageItem } from './MessageItem/MessageItem';
import styles from './Dialogs.module.css';

const Dialogs = (props) => {
  const dialogsElements = props.dialogs.map( dialog => <DialogItem name={dialog.name} id={dialog.id} /> )
  const messagesElements = props.messages.map( msg => <MessageItem message={msg.message} /> )

  const messageText = React.createRef();

  const onMessageChange = () => {
    const text = messageText.current.value;
    props.updateNewMessageText(text);
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
          <textarea onChange={onMessageChange}
                    ref={messageText}
                    value={props.newMessageText}/>
          <button onClick={ props.addMessage }>Send message</button>
        </div>
      </div>
    </div>
  );
}

export { Dialogs };