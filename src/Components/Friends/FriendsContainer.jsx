import { Friends } from './Friends';
import { connect } from 'react-redux';


const mapStateToProps = (state) => {
    return {
        friends: state.friendsReducer.friends
    }
}

const FriendsContainer = connect(mapStateToProps)(Friends);

export { FriendsContainer }