import React from 'react';
import styles from './MyPosts.module.css';
import Post from './Post/Post';

const MyPosts = (props) => {
  const postsElements = props.posts.map( post => <Post message={post.message} likesCount={post.likesCount} /> );

  const newPostElement = React.createRef();
  const onPostChange = () => {
    const text = newPostElement.current.value;
    props.updatePostText(text);
  }

  return (
    <div className={styles.MyPosts}>
      <h1>My posts</h1>
      <div className={styles.addPost}>
        <textarea onChange={onPostChange}
                  value={props.newPostText}
                  ref={newPostElement}
                  />
        <button onClick={props.addPost}>Add post</button>
      </div>
        { postsElements }
      </div>
  );
}

export { MyPosts };