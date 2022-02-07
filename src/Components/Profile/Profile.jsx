import React from 'react';
import { MyPosts } from './MyPosts/MyPosts';
import { ProfileInfo } from './ProfileInfo/ProfileInfo';

const Profile = (props) => {
    return (
        <>
            <ProfileInfo />
            <MyPosts posts={props.state.posts} newPostText={props.state.newPostText} dispatch={props.dispatch} />
        </>
    );
};

export { Profile };