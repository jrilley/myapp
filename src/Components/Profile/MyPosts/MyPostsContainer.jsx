import React from 'react';
import { addPostAC, updatePostTextAC } from '../../../redux/reducers/profileReducer';
import { MyPosts } from './MyPosts';

const MyPostsContainer = (props) => {
  const AddPost = () => {
    props.dispatch(addPostAC());
  }

  const updatePostText = (text) => {
    let action = updatePostTextAC(text);
    props.dispatch(action);
  }

  return (
    <MyPosts addPost={AddPost}
            updatePostText={updatePostText}
            posts={props.posts}
            newPostText={props.newPostText}
    />
  );
}

export { MyPostsContainer };