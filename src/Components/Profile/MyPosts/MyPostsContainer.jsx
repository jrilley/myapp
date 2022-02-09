import React from 'react';
import { addPostAC, updatePostTextAC } from '../../../redux/reducers/profileReducer';
import { StoreContext } from '../../../StoreContext';
import { MyPosts } from './MyPosts';

const MyPostsContainer = () => {
  return (
    <StoreContext.Consumer>
      {
        (store) => {
          let state = store.getState();
          const AddPost = () => {
            store.dispatch(addPostAC());
          }

          const updatePostText = (text) => {
            let action = updatePostTextAC(text);
            store.dispatch(action);
          }

          return <MyPosts addPost={AddPost}
            updatePostText={updatePostText}
            posts={state.profileReducer.posts}
            newPostText={state.profileReducer.newPostText}
          />
        }
      }
    </StoreContext.Consumer>
  );
}

export { MyPostsContainer };