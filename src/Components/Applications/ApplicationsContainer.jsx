import { Applications } from './Applications';
import { connect } from 'react-redux';
import { requestApplications, setCurrentPageAC } from '../../redux/reducers/applicationsReducer';

const mapStateToProps = state => {
    return {
        applications: state.applicationsReducer.applications,
        totalCount: state.applicationsReducer.totalCount,
        pageSize: state.applicationsReducer.pageSize,
        currentPage: state.applicationsReducer.currentPage,
        isFetching: state.applicationsReducer.isFetching,
        error: state.applicationsReducer.error,
    }
}

const ApplicationsContainer = connect(
    mapStateToProps,
    { requestApplications, setCurrentPage: setCurrentPageAC }
)(Applications);

export { ApplicationsContainer }
