from tempfile import NamedTemporaryFile

from django.core.management import call_command
from xmodule.modulestore.tests.django_utils import SharedModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory
from testfixtures import LogCapture

from course_modes.tests.factories import CourseModeFactory
from student.tests.factories import UserFactory
from student.models import CourseEnrollment, User


LOGGER_NAME = 'student.management.commands.bulk_unenroll'


class BulkUnenrollTests(SharedModuleStoreTestCase):
    def setUp(self):
        super(BulkUnenrollTests, self).setUp()
        self.course = CourseFactory.create()
        self.audit_mode = CourseModeFactory.create(
            course_id=self.course.id,
            mode_slug='audit',
            mode_display_name='Audit',
        )

        self.user_info = [
            ('amy', 'amy@pond.com', 'password'),
            ('rory', 'rory@theroman.com', 'password'),
            ('river', 'river@song.com', 'password')
        ]
        self.enrollments = []
        self.users = []

        for username, email, password in self.user_info:
            user = UserFactory.create(username=username, email=email, password=password)
            self.users.append(user)
            self.enrollments.append(CourseEnrollment.enroll(user, self.course.id, mode='audit'))

    def test_user_not_exist(self):
        with NamedTemporaryFile() as csv:
            csv.write("user_id,username,email,course_id\n")
            csv.writelines("111,test,test@example.com,course-v1:edX+DemoX+Demo_Course\n")
            csv.seek(0)

            with LogCapture(LOGGER_NAME) as log:
                call_command("bulk_unenroll", "--csv_path={}".format(csv.name))
                log.check(
                    (
                        LOGGER_NAME,
                        'WARNING',
                        'User with username {} or email {} does not exist'.format('test', 'test@example.com')
                    )
                )

    def test_invalid_course_key(self):
        with NamedTemporaryFile() as csv:
            csv.write("user_id,username,email,course_id\n")
            csv.writelines("111,amy,amy@pond.com,test_course\n")
            csv.seek(0)

            with LogCapture(LOGGER_NAME) as log:
                call_command("bulk_unenroll", "--csv_path={}".format(csv.name))
                log.check(
                    (
                        LOGGER_NAME,
                        'WARNING',
                        'Invalid or non-existant course id {}'.format('test_course')
                    )
                )

    def test_user_not_enrolled(self):
        with NamedTemporaryFile() as csv:
            csv.write("user_id,username,email,course_id\n")
            csv.writelines("111,amy,amy@pond.com,course-v1:edX+DemoX+Demo_Course\n")
            csv.seek(0)

            with LogCapture(LOGGER_NAME) as log:
                call_command("bulk_unenroll", "--csv_path={}".format(csv.name))
                log.check(
                    (
                        LOGGER_NAME,
                        'WARNING',
                        'Enrollment for the user {} in course {} does not exist!'.format(
                            'amy', 'course-v1:edX+DemoX+Demo_Course')
                    )
                )

    def test_bulk_un_enroll(self):
        with NamedTemporaryFile() as csv:
            csv.write("user_id,username,email,course_id\n")
            csv.writelines(
                str(enrollment.user.id) + "," + enrollment.user.username +
                "," + enrollment.user.email + "," + str(enrollment.course.id) + "\n"
                for enrollment in self.enrollments
            )
            csv.seek(0)

            call_command("bulk_unenroll", "--csv_path={}".format(csv.name))
            for enrollment in CourseEnrollment.objects.all():
                self.assertEqual(enrollment.is_active, False)
