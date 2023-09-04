import uuid
from django.db import models
from django.db.models.signals import post_save
from django.conf import settings

from account.models import Profile
from timetable.models import ClassDetail


class BookingRecord(models.Model):
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True)
    waitlist_update_time = models.DateTimeField(auto_now_add=True)
    schedule_update_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        item_selected, item_listed, item_booked_currently, item_booked_previously = 0, 0, 0, 0
        for x in self.booking_set.all():
            if x.is_selected:
                item_selected += 1
            elif x.is_listed:
                item_listed += 1
            elif x.is_booked_currently:
                item_booked_currently += 1
            elif x.is_booked_previously:
                item_booked_previously += 1
        try:
            return self.owner.user.username + " : " + str(item_selected) + " sel, " \
                   + str(item_listed) + " list, " + str(item_booked_currently) + " cur, " \
                   + str(item_booked_previously) + " pre"
        except AttributeError:
            return str("deleted user") + " : " + str(item_selected) + " sel, " \
                   + str(item_listed) + " list, " + str(item_booked_currently) + " cur, " \
                   + str(item_booked_previously) + " pre"


class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    booking_record = models.ForeignKey(BookingRecord, on_delete=models.CASCADE, null=True)
    class_item = models.ForeignKey(ClassDetail, on_delete=models.CASCADE, null=True)
    # cancelled after confirmed booking
    is_cancelled = models.BooleanField(default=False)
    # cancelled after listed
    is_cancelled_listed = models.BooleanField(default=False)
    # currently booked class
    is_booked_currently = models.BooleanField(default=False)
    # to keep record of previously booked class
    is_booked_previously = models.BooleanField(default=False)
    # class cancelled within 2hrs of starting time
    is_late_cancelled = models.BooleanField(default=False)
    # class more than 2 days ahead, confirmed from selection
    is_listed = models.BooleanField(default=False)
    is_selected = models.BooleanField(default=False)
    is_waitlisted = models.BooleanField(default=False)
    date_added = models.DateTimeField(auto_now_add=True)
    date_booked = models.DateTimeField(null=True)
    date_cancelled = models.DateTimeField(null=True)
    token_used = models.PositiveSmallIntegerField(default=1)
    # for cancellation (confirmed class)
    visit_id = models.CharField(max_length=9, blank=True)
    waitlist_position = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.class_item.center_schedule.date + " - " + self.class_item.start_time + " : " + \
               self.class_item.class_name


class PeriodicBooking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    booking_record = models.ForeignKey(BookingRecord, on_delete=models.CASCADE, null=True)
    start_time = models.CharField(max_length=5)
    class_name = models.CharField(max_length=100)
    teacher = models.CharField(max_length=50)
    location = models.CharField(max_length=100)
    token_set = models.PositiveSmallIntegerField(default=1)
    week_day_django = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        weekday_dict = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
                        5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
        return f"{self.class_name} with {self.teacher} at " \
               f"{self.start_time} on {weekday_dict[self.is_active]}"


def post_save_booking_record_create(sender, instance, created, *args, **kwargs):
    if created:
        BookingRecord.objects.get_or_create(owner=Profile.objects.get(user=instance))


post_save.connect(post_save_booking_record_create, sender=settings.AUTH_USER_MODEL)


