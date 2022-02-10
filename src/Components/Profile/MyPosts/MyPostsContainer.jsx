import { connect } from 'react-redux';
import { addPostAC, updatePostTextAC } from '../../../redux/reducers/profileReducer';
import { MyPosts } from './MyPosts';

const mapStateToProps = (state) => {
  return {
    posts: state.profileReducer.posts,
    newPostText: state.profileReducer.newPostText
  };
}

const mapDispatchToProps = (dispatch) => {
  return {
    addPost: () => {
      dispatch(addPostAC());
    },
    updatePostText: (text) => {
      let action = updatePostTextAC(text);
      dispatch(action);
    }
  };
}

const MyPostsContainer = connect(mapStateToProps, mapDispatchToProps)(MyPosts);

export { MyPostsContainer };