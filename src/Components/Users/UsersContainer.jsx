import { Users } from './Users';
import { connect } from 'react-redux';
import { followAC, unfollowAC, setUsersAC } from '../../redux/reducers/usersReducer';


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
        },
        setUsers: users => {
            dispatch(setUsersAC(users));
        }
    }
}

const UsersContainer = connect(mapStateToProps, mapDispatchToProps)(Users);

export { UsersContainer }