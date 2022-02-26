import { Users } from './Users';
import { connect } from 'react-redux';
import { followAC, unfollowAC, setUsersAC, setUsersTotalCountAC, setCurrentPageAC } from '../../redux/reducers/usersReducer';


const mapStateToProps = state => {
    return {
        users: state.usersReducer.users,
        totalCount: state.usersReducer.totalCount,
        pageSize: state.usersReducer.pageSize,
        currentPage: state.usersReducer.currentPage,
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
            dispatch(setUsersAC(users))
        },
        setUsersTotalCount: totalCount => {
            dispatch(setUsersTotalCountAC(totalCount))
        },
        setCurrentPage: currentPage => {
            dispatch(setCurrentPageAC(currentPage))
        }
    }
}

const UsersContainer = connect(mapStateToProps, mapDispatchToProps)(Users);

export { UsersContainer }