"""
Advanced service demonstrating production database patterns.

Patterns covered:
  1. **Transaction + Row Locking** — atomic bulk enrollment with `with_for_update()`
  2. **N+1 Prevention** — instructor dashboard via `selectinload` / `joinedload`
  3. **Bulk Insert + Atomic Rollback** — batch-insert courses, full rollback on failure
  4. **Aggregation + Subquery Optimization** — enrollment analytics using `func` / `group_by`
  5. **Pessimistic Locking + Deadlock Avoidance** — transfer enrollment with ordered locking
"""

from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import select, func, case

import structlog

from fastapi import BackgroundTasks
from app.models.course import Course, Enrollment, Lesson
from app.models.user import User, Instructor
from app.schemas.advanced import (
    BulkEnrollRequest,
    BulkCourseCreateRequest,
    TransferEnrollmentRequest,
)
from app.core.exceptions import (
    NotFoundException,
    ConflictException,
    ValidationException,
    AppException,
)
from app.core.redis import clear_cache
from app.core.tasks import BackgroundTaskManager
from app.services.email_service import EmailService
from app.core.config import settings

logger = structlog.get_logger(__name__)


class AdvancedService:
    def __init__(self, db: Session):
        self.db = db

    # ──────────────────────────────────────────────────────────────────────
    # 1. CONCURRENT ENROLLMENT  (Transaction + Row Locking)
    #
    # Enroll multiple users in a single course within one transaction.
    # The course row is locked with `with_for_update()` to prevent
    # over-enrollment when concurrent requests hit the same endpoint.
    # ──────────────────────────────────────────────────────────────────────

    def concurrent_enroll(self, req: BulkEnrollRequest, background_tasks: BackgroundTasks = None) -> dict:
        """
        Atomically enroll multiple users in a course.

        Uses `SELECT ... FOR UPDATE` on the course row so concurrent
        requests cannot exceed `max_students`.  If any step fails the
        entire transaction is rolled back — no partial enrollments.
        """
        try:
            # Lock the course row to prevent race conditions
            stmt = (
                select(Course)
                .filter(Course.id == req.course_id)
                .with_for_update()
            )
            course = self.db.execute(stmt).scalar_one_or_none()
            if not course:
                raise NotFoundException("Course", req.course_id)

            # Current enrollment count (inside the lock)
            current_count = self.db.scalar(
                select(func.count(Enrollment.id))
                .filter(Enrollment.course_id == req.course_id)
            )
            if current_count + len(req.user_ids) > course.max_students:
                raise ValidationException(
                    f"Cannot enroll {len(req.user_ids)} users — only "
                    f"{course.max_students - current_count} seats remaining"
                )

            # Verify all users exist
            existing_users = (
                self.db.execute(
                    select(User).filter(User.id.in_(req.user_ids))
                ).scalars().all()
            )
            found_ids = {u.id for u in existing_users}
            missing = set(req.user_ids) - found_ids
            if missing:
                raise NotFoundException("Users", ", ".join(str(i) for i in missing))

            # Check for duplicate enrollments
            already_enrolled = set(
                self.db.execute(
                    select(Enrollment.user_id).filter(
                        Enrollment.course_id == req.course_id,
                        Enrollment.user_id.in_(req.user_ids),
                    )
                ).scalars().all()
            )
            if already_enrolled:
                raise ConflictException(
                    f"Users {already_enrolled} are already enrolled"
                )

            # Batch-insert enrollments
            new_enrollments = []
            for user_id in req.user_ids:
                enrollment = Enrollment(user_id=user_id, course_id=req.course_id)
                self.db.add(enrollment)
                new_enrollments.append(enrollment)

            self.db.flush()  # Assign IDs without committing
            enrollment_ids = [e.id for e in new_enrollments]
            self.db.commit()

            clear_cache("*:courses:*")
            logger.info(
                "bulk_enrollment_success",
                course_id=req.course_id,
                count=len(enrollment_ids),
            )

            # Background: send confirmation emails
            task_manager = BackgroundTaskManager(self.db)
            if background_tasks:
                for user in existing_users:
                    background_tasks.add_task(
                        task_manager.execute_with_retry,
                        self._send_bulk_enrollment_email,
                        user.email,
                        course.title,
                    )
            else:
                for user in existing_users:
                    task_manager.execute_with_retry(
                        self._send_bulk_enrollment_email,
                        user.email,
                        course.title,
                    )

            return {
                "status": "success",
                "enrolled_count": len(enrollment_ids),
                "enrollment_ids": enrollment_ids,
            }

        except (NotFoundException, ConflictException, ValidationException):
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.error("concurrent_enroll_failed", error=str(exc))
            raise AppException("Concurrent enrollment transaction failed")

    # ──────────────────────────────────────────────────────────────────────
    # 2. INSTRUCTOR DASHBOARD  (N+1 Prevention)
    #
    # Without eager loading, fetching an instructor's courses → lessons →
    # enrollments would fire O(N × M) queries.  Using `selectinload` for
    # collections and `joinedload` for single-row relations keeps it at a
    # constant number of queries regardless of data size.
    # ──────────────────────────────────────────────────────────────────────

    def get_instructor_dashboard(self, instructor_id: int) -> dict:
        """
        Fetch a rich instructor overview in 3–4 queries (not N+1).

        Query plan:
          1. SELECT instructor JOIN user
          2. SELECT courses WHERE instructor_id = ?
          3. SELECT lessons WHERE course_id IN (...)  — via selectinload
          4. Aggregate enrollment counts per course
        """
        stmt = (
            select(Instructor)
            .options(
                joinedload(Instructor.user),
                selectinload(Instructor.courses)
                .selectinload(Course.lessons),
            )
            .filter(Instructor.id == instructor_id)
        )
        instructor = self.db.execute(stmt).unique().scalar_one_or_none()
        if not instructor:
            raise NotFoundException("Instructor", instructor_id)

        # Separate aggregate query for enrollment counts (avoids cartesian join)
        course_ids = [c.id for c in instructor.courses]
        enrollment_counts: dict[int, int] = {}
        if course_ids:
            rows = self.db.execute(
                select(
                    Enrollment.course_id,
                    func.count(Enrollment.id).label("cnt"),
                )
                .filter(Enrollment.course_id.in_(course_ids))
                .group_by(Enrollment.course_id)
            ).all()
            enrollment_counts = {row.course_id: row.cnt for row in rows}

        total_students = sum(enrollment_counts.values())

        courses_data = []
        for course in instructor.courses:
            courses_data.append({
                "id": course.id,
                "title": course.title,
                "enrollment_count": enrollment_counts.get(course.id, 0),
                "lessons": [
                    {"id": l.id, "title": l.title, "lesson_order": l.lesson_order}
                    for l in sorted(course.lessons, key=lambda x: x.lesson_order)
                ],
            })

        return {
            "instructor_id": instructor.id,
            "specialization": instructor.specialization,
            "rating": instructor.rating,
            "total_students": total_students,
            "courses": courses_data,
        }

    # ──────────────────────────────────────────────────────────────────────
    # 3. BULK COURSE CREATION  (Atomic Transaction + Rollback)
    #
    # All courses are inserted within a single transaction.  If any
    # single insert fails (e.g. FK violation), the entire batch is rolled
    # back so the database never contains a half-created set.
    # ──────────────────────────────────────────────────────────────────────

    def bulk_create_courses(self, req: BulkCourseCreateRequest) -> dict:
        """
        Atomically create multiple courses.

        On any failure the transaction rolls back entirely — no partial
        state is persisted.
        """
        try:
            new_courses = []
            for item in req.courses:
                course = Course(**item.model_dump())
                self.db.add(course)
                new_courses.append(course)

            self.db.flush()  # Assign IDs before commit
            course_ids = [c.id for c in new_courses]
            self.db.commit()

            clear_cache("*:courses:*")
            logger.info("bulk_create_courses_success", count=len(course_ids))

            return {
                "status": "success",
                "created_count": len(course_ids),
                "course_ids": course_ids,
            }

        except Exception as exc:
            self.db.rollback()
            logger.error("bulk_create_courses_failed", error=str(exc))
            raise AppException(f"Bulk course creation failed: {exc}")

    # ──────────────────────────────────────────────────────────────────────
    # 4. COURSE ANALYTICS  (Aggregation + Subquery Optimization)
    #
    # Instead of loading every enrollment row and computing in Python,
    # this pushes the aggregation into the database using `func.count`,
    # `func.avg`, conditional `case`, and `group_by`.
    # ──────────────────────────────────────────────────────────────────────

    def get_course_analytics(self) -> dict:
        """
        Compute enrollment statistics per course in a single query.

        Metrics: enrollment_count, completion_rate, average progress.
        """
        stmt = (
            select(
                Course.id.label("course_id"),
                Course.title.label("course_title"),
                func.count(Enrollment.id).label("enrollment_count"),
                # Completion rate = completed enrollments / total enrollments
                func.coalesce(
                    func.avg(
                        case(
                            (Enrollment.completed == True, 100.0),  # noqa: E712
                            else_=0.0,
                        )
                    ),
                    0.0,
                ).label("completion_rate"),
                func.coalesce(func.avg(Enrollment.progress), 0.0).label("avg_progress"),
            )
            .outerjoin(Enrollment, Course.id == Enrollment.course_id)
            .group_by(Course.id, Course.title)
            .order_by(func.count(Enrollment.id).desc())
        )

        rows = self.db.execute(stmt).all()

        courses = [
            {
                "course_id": row.course_id,
                "course_title": row.course_title,
                "enrollment_count": row.enrollment_count,
                "completion_rate": round(float(row.completion_rate), 2),
                "avg_progress": round(float(row.avg_progress), 2),
            }
            for row in rows
        ]

        return {"courses": courses, "total_courses": len(courses)}

    # ──────────────────────────────────────────────────────────────────────
    # 5. TRANSFER ENROLLMENT  (Pessimistic Locking + Deadlock Avoidance)
    #
    # Locking two course rows in a consistent order (by ID) prevents
    # deadlocks when two concurrent requests transfer in opposite
    # directions (A→B vs B→A).
    # ──────────────────────────────────────────────────────────────────────

    def transfer_enrollment(self, req: TransferEnrollmentRequest) -> dict:
        """
        Move a student from one course to another atomically.

        Acquires row-level locks on both courses in ascending ID order
        to prevent deadlocks under concurrent transfers.
        """
        try:
            # Order lock acquisition by ID to prevent deadlocks
            first_id, second_id = sorted([req.from_course_id, req.to_course_id])

            first_course = self.db.execute(
                select(Course).filter(Course.id == first_id).with_for_update()
            ).scalar_one_or_none()
            second_course = self.db.execute(
                select(Course).filter(Course.id == second_id).with_for_update()
            ).scalar_one_or_none()

            if not first_course or not second_course:
                missing = req.from_course_id if not first_course else req.to_course_id
                raise NotFoundException("Course", missing)

            # Map back to named references
            from_course = first_course if first_id == req.from_course_id else second_course
            to_course = second_course if second_id == req.to_course_id else first_course
            target_course = to_course 

            # Verify enrollment exists in source course
            enrollment = self.db.execute(
                select(Enrollment).filter(
                    Enrollment.user_id == req.user_id,
                    Enrollment.course_id == req.from_course_id,
                )
            ).scalar_one_or_none()
            if not enrollment:
                raise NotFoundException("Enrollment", f"user={req.user_id}, course={req.from_course_id}")

            # Verify no duplicate in target course
            existing_target = self.db.execute(
                select(Enrollment).filter(
                    Enrollment.user_id == req.user_id,
                    Enrollment.course_id == req.to_course_id,
                )
            ).scalar_one_or_none()
            if existing_target:
                raise ConflictException("User is already enrolled in the target course")

            # Check capacity on target course
            target_count = self.db.scalar(
                select(func.count(Enrollment.id))
                .filter(Enrollment.course_id == req.to_course_id)
            )
            if target_count >= target_course.max_students:
                raise ValidationException("Target course is full")

            # Perform the transfer: delete old → create new
            self.db.delete(enrollment)
            self.db.flush()

            new_enrollment = Enrollment(
                user_id=req.user_id,
                course_id=req.to_course_id,
            )
            self.db.add(new_enrollment)
            self.db.flush()
            self.db.commit()

            clear_cache("*:courses:*")
            logger.info(
                "enrollment_transferred",
                user_id=req.user_id,
                from_course=req.from_course_id,
                to_course=req.to_course_id,
            )

            return {
                "status": "success",
                "new_enrollment_id": new_enrollment.id,
                "from_course_id": req.from_course_id,
                "to_course_id": req.to_course_id,
            }

        except (NotFoundException, ConflictException, ValidationException):
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.error("transfer_enrollment_failed", error=str(exc))
            raise AppException("Enrollment transfer failed")

    # ── Email Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _send_bulk_enrollment_email(user_email: str, course_title: str):
        """Background task: send bulk enrollment confirmation email."""
        EmailService.send_email(
            to_email=user_email,
            subject=f"Enrolled in {course_title}",
            template_path=f"{settings.EMAIL_TEMPLATE_DIR}/bulk_enrollment.html",
            context={"course_title": course_title, "email": user_email},
        )
