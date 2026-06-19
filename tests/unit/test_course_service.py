from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.course import Course, Enrollment
from app.models.user import User
from app.schemas.course import CourseCreate
from app.services.course_service import CourseService


@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def course_service(mock_db):
    return CourseService(mock_db)

def test_get_course_success(course_service, mock_db):
    # Setup
    mock_course = MagicMock(spec=Course)
    mock_course.id = 1
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_course

    # Execute
    course = course_service.get_course(1)

    # Assert
    assert course.id == 1
    mock_db.execute.assert_called_once()

def test_get_course_not_found(course_service, mock_db):
    # Setup
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    # Execute & Assert
    with pytest.raises(NotFoundException):
        course_service.get_course(999)

def test_create_course_success(course_service, mock_db):
    # Setup
    course_in = CourseCreate(
        title="New Course",
        description="Desc",
        category_id=1,
        max_students=10
    )

    with patch("app.services.course_service.clear_cache"):
        # Execute
        course = course_service.create_course(course_in)

        # Assert
        assert course.title == "New Course"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

def test_enroll_in_course_full(course_service, mock_db):
    # Setup
    mock_course = MagicMock(spec=Course)
    mock_course.max_students = 10
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_course
    mock_db.scalar.return_value = 10  # Already 10 students

    mock_user = MagicMock(spec=User)
    mock_user.id = 1

    # Execute & Assert
    with pytest.raises(ValidationException, match="Course is full"):
        course_service.enroll_in_course(course_id=1, current_user=mock_user)

def test_enroll_in_course_already_enrolled(course_service, mock_db):
    # Setup
    mock_course = MagicMock(spec=Course)
    mock_course.max_students = 10

    # First call to execute returns course
    # Second call to execute returns existing enrollment
    mock_db.execute.return_value.scalar_one_or_none.side_effect = [mock_course, MagicMock(spec=Enrollment)]

    mock_user = MagicMock(spec=User)
    mock_user.id = 1

    # Execute & Assert
    with pytest.raises(ConflictException, match="Already enrolled"):
        course_service.enroll_in_course(course_id=1, current_user=mock_user)
