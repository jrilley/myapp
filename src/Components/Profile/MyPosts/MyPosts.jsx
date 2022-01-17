import React from 'react';
import styles from './MyPosts.module.css';
import Post from './Post/Post';

const MyPosts = (props) => {
  const postsElements = props.posts.map( post => <Post message={post.message} likesCount={post.likesCount} /> );

  const newPostElement = React.createRef();

  const AddPost = () => {
    const text = newPostElement.current.value;
    
    props.addPost(text);
    newPostElement.current.value = '';
  }

  return (
    <div className={styles.MyPosts}>
      <h1>My posts</h1>
      <div className={styles.addPost}>
        <textarea ref={newPostElement}></textarea>
        <button onClick={AddPost}>Add post</button>
      </div>
        { postsElements }
      </div>
  );
}

export { MyPosts };