import React from 'react';
import styles from './MyPosts.module.css';
import Post from './Post/Post';
import { addPostAC, updatePostTextAC } from '../../../redux/reducers/profileReducer';

const MyPosts = (props) => {
  const postsElements = props.posts.map( post => <Post message={post.message} likesCount={post.likesCount} /> );

  const newPostElement = React.createRef();

  const AddPost = () => {
    props.dispatch(addPostAC());
  }

  const updatePostText = () => {
    const text = newPostElement.current.value;

    props.dispatch(updatePostTextAC(text));
  }

  return (
    <div className={styles.MyPosts}>
      <h1>My posts</h1>
      <div className={styles.addPost}>
        <textarea onChange={updatePostText}
                  value={props.newPostText}
                  ref={newPostElement}
                  />
        <button onClick={AddPost}>Add post</button>
      </div>
        { postsElements }
      </div>
  );
}

export { MyPosts };