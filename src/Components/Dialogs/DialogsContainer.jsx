import { connect } from 'react-redux';
import { addMessageAC, updateMessageTextAC } from '../../redux/reducers/dialogsReducer';
import { Dialogs } from './Dialogs';

const mapStateToProps = (state) => {
  return {
    dialogsReducer: state.dialogsReducer
  }
}

const mapDispatchToProps = (dispatch) => {
  return {
    addMessage: () => {
      dispatch(addMessageAC());
    },
    updateNewMessageText: (text) => {
      let action = updateMessageTextAC(text)
      dispatch(action);
    }
  }
}

const DialogsContainer = connect(mapStateToProps, mapDispatchToProps)(Dialogs);

export { DialogsContainer };