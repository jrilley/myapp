import React from 'react';
import { MyPostsContainer } from './MyPosts/MyPostsContainer';
import { ProfileInfo } from './ProfileInfo/ProfileInfo';

const Profile = (props) => {
    return (
        <>
            <ProfileInfo />
            <MyPostsContainer posts={props.state.posts} newPostText={props.state.newPostText} dispatch={props.dispatch} />
        </>
    );
};

export { Profile };