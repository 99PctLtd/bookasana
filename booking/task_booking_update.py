# schedule_update should be ran every hour automatically to check on update
from __future__ import absolute_import
from booking.models import Booking, PeriodicBooking
from timetable.models import ClassDetail
from celery import shared_task
from datetime import datetime, timedelta
import time


@shared_task()
def booking_update():
    # runs every day at 00:00
    # move confirmed booking from the past to my history
    # mindbody only update this once at 00:00
    for booking in Booking.objects.filter(is_booked_currently=True):
        if booking.class_item.date_time_field < datetime.now():
            set_booking_status_single(booking, is_booked_previously=True)
            print(f"{booking.booking_record.owner.user.username}'s {booking} "
                  f"is set to history.")
    # delete selected item two hours before class start time if it is never confirmed
    for booking in Booking.objects.filter(is_selected=True):
        if (booking.class_item.date_time_field - datetime.now()).total_seconds() / 60 < 120:
            print(f"{booking.booking_record.owner.user.username}'s {booking} "
                  f"is deleted, it was never confirmed 2 hours before class "
                  f"from selection list")
            booking.delete()
    # delete waitlist item if it is never confirmed
    for booking in Booking.objects.filter(is_waitlisted=True):
        if booking.class_item.date_time_field.date() < datetime.now().date():
            print(f"{booking.booking_record.owner.user.username}'s {booking} "
                  f"is deleted, it was never confirmed from waitlist.")
            booking.delete()


@shared_task()
def booking_update_15():
    # runs every 15 mins
    # delete selected item two hours before class start time if it is never confirmed
    for booking in Booking.objects.filter(is_selected=True):
        if (booking.class_item.date_time_field - datetime.now()).total_seconds() / 60 < 120:
            print(f"{booking.booking_record.owner.user.username}'s {booking} "
                  f"is deleted, it was never confirmed 2 hours before class "
                  f"from selection list")
            booking.delete()


@shared_task()
def booking_update_0900():
    # runs every day at 08:59:59
    # update selected items token to 0 if it is now less than 2 days away
    time.sleep(59)
    for booking in Booking.objects.filter(is_selected=True):
        if booking.class_item.date_time_field.day - datetime.now().day <= 2:
            booking.token_used = 0
            booking.save()


def set_booking_status_single(booking_item, **kwargs):
    booking_item.is_booked_currently = kwargs.get("is_booked_currently", False)
    booking_item.is_booked_previously = kwargs.get("is_booked_previously", False)
    booking_item.is_cancelled = kwargs.get("is_cancelled", False)
    booking_item.is_cancelled_listed = kwargs.get("is_cancelled_listed", False)
    booking_item.is_late_cancelled = kwargs.get("is_late_cancelled", False)
    booking_item.is_listed = kwargs.get("is_listed", False)
    booking_item.is_selected = kwargs.get("is_selected", False)
    booking_item.is_waitlisted = kwargs.get("is_waitlisted", False)
    if kwargs.get("is_booked_currently"):
        booking_item.date_booked = datetime.now()
    if kwargs.get("is_cancelled") or kwargs.get("is_late_cancelled"):
        booking_item.date_cancelled = datetime.now()
    if kwargs.get("is_listed"):
        booking_item.date_added = datetime.now()
    booking_item.save()
    pass


@shared_task()
def weekly_periodic_booking_update():
    print(f"updating bookings from periodic booking list...")
    print(f'==================================================')
    # runs every day at 02:00
    # check between the next 2 - 7 days
    start_date = datetime.today().date() + timedelta(days=2)
    end_date = datetime.today().date() + timedelta(days=10)
    # gather users listed bookings in the next 2 - 7 days
    future_week_bookings = Booking.objects.filter(
        class_item__date_time_field__range=(start_date, end_date))
    # gather class items in the next 2 - 7 days
    future_week_class_details = ClassDetail.objects.filter(
        date_time_field__range=(start_date, end_date))
    # gather all active periodic bookings
    periodic_bookings = PeriodicBooking.objects.filter(is_active=True)
    for pb in periodic_bookings:
        # check periodic_bookings against future_week_bookings
        bookings = future_week_bookings.filter(
            class_item__date_time_field__week_day=pb.week_day_django,
            booking_record=pb.booking_record,
            class_item__start_time=pb.start_time,
            class_item__location=pb.location,
            class_item__teacher=pb.teacher,
            class_item__class_name=pb.class_name
        )
        # if not yet listed in future_week_bookings
        # check against future_week_class_details
        if not bookings.exists():
            class_details = future_week_class_details.filter(
                date_time_field__week_day=pb.week_day_django,
                start_time=pb.start_time,
                location=pb.location,
                teacher=pb.teacher,
                class_name=pb.class_name
            )
            # if periodic booking exists in class future_week_class_details
            # add item to booking list
            if class_details.exists():
                if (class_details[0].date_time_field.date() - datetime.now().date()).days > 2:
                    # check if user has sufficient token for next day booking
                    if pb.token_set == 0 or pb.booking_record.owner.token_single - pb.token_set >= 0:
                        # prevent booking class between 11pm to 9am
                        booking = Booking.objects.create(
                            booking_record=pb.booking_record,
                            class_item=class_details[0],
                            is_listed=True,
                            token_used=pb.token_set,
                        )
                        print(f"{booking.booking_record.owner.user.username} : {booking} is listed.")
                    else:
                        # insufficient token balance for adding class to list
                        # potentially leave message/notification for user
                        pass
            else:
                print(f"{pb.booking_record.owner.user.username} : "
                      f"{pb} is not yet in the schedule in the coming week.")
        else:
            if bookings[0].is_selected:
                set_booking_status_single(bookings[0], is_listed=True)
                print(f"{bookings[0].booking_record.owner.user.username} : "
                      f"{bookings[0]} is added to listed from selection.")
            elif bookings[0].is_cancelled_listed:
                print(f"{bookings[0].booking_record.owner.user.username} : "
                      f"{bookings[0]} removed from list by user, will skip listing this week.")
            elif bookings[0].is_listed:
                print(f"{bookings[0].booking_record.owner.user.username} : "
                      f"{bookings[0]} is already listed.")
    # to clean up inactive periodic bookings -
    # items with no repeated booking in last two months
    days_ago_60 = datetime.today() - timedelta(days=60)
    days_ago_60_bookings = Booking.objects.filter(
        class_item__date_time_field__gte=days_ago_60)
    for pb in periodic_bookings:
        # check periodic_bookings against future_week_bookings
        bookings = days_ago_60_bookings.filter(
            class_item__date_time_field__week_day=pb.week_day_django,
            booking_record=pb.booking_record,
            class_item__start_time=pb.start_time,
            class_item__location=pb.location,
            class_item__teacher=pb.teacher,
            class_item__class_name=pb.class_name
        )
        if not bookings.exists():
            pb.is_active = False
            pb.save()
