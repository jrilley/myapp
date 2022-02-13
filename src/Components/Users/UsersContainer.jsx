import { Users } from './Users';
import { connect } from 'react-redux';
import { followAC, unfollowAC } from '../../redux/reducers/usersReducer';


const mapStateToProps = state => {
    return {
        users: state.usersReducer.users
    }
}

const mapDispatchToProps = dispatch => {
    return {
        follow: userId => {
            dispatch(followAC(userId))
        },
        unfollow: userId => {
            dispatch(unfollowAC(userId))
        }
    }
}

const UsersContainer = connect(mapStateToProps, mapDispatchToProps)(Users);

export { UsersContainer }