import React from 'react';
import avatar from '../Profile/images/ava.jpg';
import { FriendItem } from './FriendItem/FriendItem';
import { StoreContext } from '../../StoreContext';
import { Friends } from './Friends';

const FriendsContainer = () => {
    return (
        <StoreContext.Consumer>
            {
                (store) => {
                    let state = store.getState();
                    const friendsElements = state.friendsReducer.friends.map(f => <FriendItem avatar={avatar} name={f.name} />);
                    return <Friends friendsElements={friendsElements} />
                }
            }
        </StoreContext.Consumer>
    );
}

export { FriendsContainer }