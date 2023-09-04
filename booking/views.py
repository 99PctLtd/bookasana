import calendar
import operator
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from functools import reduce
from django.db.models import Q
from django.db.models.query import QuerySet
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.generic import View

from account.models import Profile
from booking.models import Booking, BookingRecord, PeriodicBooking
from timetable.models import ClassDetail

from datetime import date, datetime, timedelta
from .book_class import (
    book_single,
    cancel_single,
    cancel_wait_item,
    update_user_schedule,
    update_user_waitlist,
)
from .forms import BookingTokenForm


@login_required()
def add_to_repeat_weekly(request, booking_id):
    booking = Booking.objects.filter(id=booking_id)
    if booking.exists():
        if request.user == booking[0].booking_record.owner.user:
            pb, is_created = PeriodicBooking.objects.get_or_create(
                booking_record=booking[0].booking_record,
                start_time=booking[0].class_item.start_time,
                class_name=booking[0].class_item.class_name,
                teacher=booking[0].class_item.teacher,
                location=booking[0].class_item.location,
                token_set=booking[0].token_used if booking[0].token_used > 0 else 1,
                week_day_django=to_django_weekday(
                    booking[0].class_item.date_time_field),
            )
            messages.success(request, f"{pb.class_name} with {pb.teacher} at {pb.start_time} "
                                      f"is set to repeat weekly on {to_django_weekday_name(pb.week_day_django)}.")
        else:
            messages.error(request, f"You don't have permission to modify this booking.")
    else:
        messages.error(request, f"Requested booking does not exist.")
    return redirect(reverse('booking:my_class'))


@login_required()
def add_to_selection_schedule(request, class_id):
    user_profile = get_object_or_404(Profile, user=request.user)
    class_item = ClassDetail.objects.get(id=class_id)
    booking_record, status = BookingRecord.objects.get_or_create(owner=user_profile)
    # to prevent any class selection before 9am the next morning after booking period is closed (11pm - 9am)
    if convert_time(request, "11:00 pm") < datetime.now().time() or \
            datetime.now().time() < convert_time(request, "9:00 am"):
        class_detail = ClassDetail.objects.get(id=class_id)
        if ((class_detail.date_time_field - datetime.now()).total_seconds() / 3600) < 12:
            if class_detail.date_time_field.time() < datetime.strptime("9:00 am", '%I:%M %p').time():
                messages.error(request, f"{class_detail.class_name} with {class_detail.teacher} "
                                        f"is before 9:00 am tomorrow, it is not possible to book "
                                        f"that class.")
                return redirect(reverse('schedule:schedule') + "#class_" + str(class_id))
    if location_is_valid(request, user_profile, class_item) and class_is_valid(request, class_item):
        booking = Booking.objects.create(booking_record=booking_record,
                                         class_item=class_item,
                                         is_selected=True)
        set_token_used(booking)
        messages.info(request, f"You have selectected {booking.class_item.class_name} "
                               f"with {booking.class_item.teacher}. Confirm selections "
                               f"to add to booking list.")
        return redirect(reverse('schedule:schedule') + "#class_" + str(class_id))
    else:
        return redirect(reverse('schedule:schedule') + "#class_" + str(class_id))


@login_required()
def class_is_valid(request, class_item):
    # check if booking is current
    # in case client select past class from page idle for 3 hours
    if class_item.date_time_field > datetime.now() + timedelta(hours=2):
        if get_user_future(request):
            for user_future in get_user_future(request):
                # check if new class is on same date as listed classes
                if int(class_item.date_time_field.strftime('%d')) - \
                        int(user_future.class_item.date_time_field.strftime('%d')) == 0:
                    # check to decide which class happens earlier,
                    # use the earlier class' duration for validation
                    if class_item.date_time_field > user_future.class_item.date_time_field:
                        # new user_future class happens earlier than previously
                        # user_future class, new seletected class duration is used
                        if (class_item.date_time_field -
                            user_future.class_item.date_time_field).seconds / 60 > \
                                int(user_future.class_item.duration[:-5]):
                            # OK: no conflict
                            pass
                        elif (class_item.date_time_field -
                              user_future.class_item.date_time_field).seconds / 60 == \
                                int(user_future.class_item.duration[:-5]):
                            if class_item.location == user_future.class_item.location:
                                # OK: back to back class at same location
                                pass
                            else:
                                # OK: back to back class at different location
                                messages.warning(request, f"You are booking back to back class from different center, "
                                                          f"please make sure to leave enough time to commute.")
                                pass
                        else:
                            # ERROR: new user_future class overlap with previously user_future class
                            messages.error(request, f"{user_future.class_item.class_name} at "
                                                    f"{user_future.class_item.start_time} will "
                                                    f"not finish before {class_item.class_name} "
                                                    f"starts at {class_item.start_time}.")
                            return False
                    elif class_item.date_time_field < user_future.class_item.date_time_field:
                        # new user_future class happens later than previously user_future class,
                        # previously seletected class duration is used
                        if (user_future.class_item.date_time_field - class_item.date_time_field).seconds / 60 > \
                                int(class_item.duration[:-5]):
                            # OK: no conflict
                            pass
                        elif (user_future.class_item.date_time_field -
                              class_item.date_time_field).seconds / 60 == int(class_item.duration[:-5]):
                            if class_item.location == user_future.class_item.location:
                                # OK: back to back class at same location
                                pass
                            else:
                                # OK: back to back class at different location
                                messages.warning(request, f"You are booking back to back class from different center, "
                                                          f"please make sure to leave enough time to commute.")
                                pass
                        else:
                            # ERROR: new user_future class overlap with previously user_future class
                            messages.error(request, f"{class_item.class_name} at "
                                                    f"{class_item.start_time} will "
                                                    f"not finish before {user_future.class_item.class_name} "
                                                    f"starts at {user_future.class_item.start_time}.")
                            return False
                    else:
                        # ERROR: both classes happens on same time
                        messages.error(request, f"You cannot be at two different classes at "
                                                f"the same time, please consider other classes.")
                        return False
        return True
    else:
        messages.error(request, f"{class_item.class_name} with {class_item.teacher} "
                                f"is no longer available for booking.")
        return False


@login_required()
def confirm_selection_all(request):
    user = request.user
    profile = get_object_or_404(Profile, user=user)
    user_selection = get_user_selected(request)
    if multiple_classes_within_2_days(user_selection):
        # setup for channel
        group_name = user.username
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': f"We are proceeding to book class, please be patient. "
                               f"Refreshing page now may cause error...",
                    'level': "warning",
                }
            }
        )
    if user_selection:
        for selection in user_selection:
            if selection.token_used == 0 or \
                    profile.token_single >= profile.get_token_needed() + selection.token_used:
                confirm_selection_single(request, selection.id)
            else:
                messages.error(request, f"There is insufficient amount of token in your account to "
                                        f"list more class, please top-up your account before "
                                        f"listing another class.")
                return redirect('shopping_cart:shopping_top_up')
    else:
        messages.warning(request, f"You have not selected any class")
        return redirect('schedule:schedule')
    return redirect('booking:my_class')


def multiple_classes_within_2_days(user_selection):
    counter = 0
    if 9 < datetime.now().hour < 23:
        for us in user_selection:
            if us.class_item.date_time_field.day - datetime.now().day <= 2:
                counter += 1
    if counter > 0:
        return True
    return False


# check add before 11pm
@login_required()
def confirm_selection_single(request, booking_id):
    user = request.user
    profile = get_object_or_404(Profile, user=user)
    booking = Booking.objects.filter(id=booking_id)
    if booking.exists() and request.user == booking[0].booking_record.owner.user:
        # check if user has enough token for all listed bookings
        if booking[0].token_used == 0 or \
                profile.token_single >= profile.get_token_needed() + booking[0].token_used:
            # check if operation is done between 12pm to 9am
            if datetime.now().hour < 9:
                if int((booking[0].class_item.date_time_field.date() - datetime.today().date()).days) <= 1:
                    return confirm_listed_single(request, booking_id)
                else:
                    set_booking_status_single(booking[0], is_listed=True)
                    messages.info(request, f"{booking[0].class_item.class_name} with "
                                           f"{booking[0].class_item.teacher} is added "
                                           f"to booking list.")
                return redirect('booking:my_class')
            else:
                if int((booking[0].class_item.date_time_field.date() - datetime.today().date()).days) <= 2:
                    return confirm_listed_single(request, booking_id)
                else:
                    set_booking_status_single(booking[0], is_listed=True)
                    messages.info(request, f"{booking[0].class_item.class_name} with "
                                           f"{booking[0].class_item.teacher} is added "
                                           f"to booking list.")
        else:
            messages.error(request, f"There is insufficient amount of token in your account to "
                                    f"list more class, please top-up your account before "
                                    f"listing another class.")
            return redirect('shopping_cart:shopping_top_up')
    return redirect('booking:my_class')


@login_required()
def confirm_listed_execute(request, booking):
    user = request.user
    user_profile = get_object_or_404(Profile, user=user)
    set_token_used(booking)
    # check if listed class is within two days
    if (booking.class_item.date_time_field.date() - datetime.now().date()).days > 2:
        # check if user has sufficient token for next day booking
        if booking.token_used == 0 or user_profile.token_single > 0:
            # prevent booking class between 11pm to 9am
            if datetime.strptime("9:00 am", '%I:%M %p').time() < \
                    datetime.now().time() < \
                    datetime.strptime("11:00 pm", '%I:%M %p').time():
                # script will never reach here...
                # class outside of 2 days reservation period
                # meaning it can never be confirmed on the day
                if booking:
                    set_booking_status_single(booking, is_booked_currently=True)
                    confirm_token_spent(request, booking.token_used)
                    messages.success(request, f"{booking.class_item.class_name} is confirmed.")
            else:
                set_booking_status_single(booking, is_listed=True)
                messages.info(request, f"It is outside of scheduling period. "
                                       f"{booking.class_item.class_name} with "
                                       f"{booking.class_item.teacher} "
                                       f"will be booked the follow morning at 9:00 am.")
        else:
            messages.error(request, f"There is insufficient amount of token in your account to "
                                    f"book class, please top-up your account.")
    # booking class within 2 days
    else:
        # prevent booking class between 11pm to 9am
        if datetime.strptime("9:00 am", '%I:%M %p').time() < \
                datetime.now().time() < \
                datetime.strptime("11:00 pm", '%I:%M %p').time():
            is_booked = book_single(request, booking)
            if is_booked:
                if booking.waitlist_position == 0:
                    # successfully booked
                    set_booking_status_single(booking, is_booked_currently=True)
                else:
                    # waitlisted
                    set_booking_status_single(booking, is_waitlisted=True)
            else:
                # not able to book class, delete from listed
                booking.delete()
        else:
            set_booking_status_single(booking, is_listed=True)
            messages.info(request, f"It is outside of scheduling period. "
                                   f"{booking.class_item.class_name} with "
                                   f"{booking.class_item.teacher} will be "
                                   f"booked the follow morning at 9:00 am.")


@login_required()
def confirm_listed_single(request, booking_id):
    booking = Booking.objects.get(id=booking_id)
    confirm_listed_execute(request, booking)
    return redirect('booking:my_class')


@login_required()
def confirm_token_spent(request, token_used):
    user_profile = get_object_or_404(Profile, user=request.user)
    user_profile.token_single = user_profile.token_single - token_used
    user_profile.save()
    pass


@login_required()
def convert_time(request, time_to_convert):
    return datetime.strptime(time_to_convert, '%I:%M %p').time()


@login_required()
def delete_from_booked(request, booking_id):
    # check if item exists
    booking = Booking.objects.filter(id=booking_id)
    if booking.exists():
        # check if item belongs to user
        if request.user == booking[0].booking_record.owner.user:
            # Proceed to cancel from Pure and get response if it is late cancel
            cancel_single.delay(request.user.id, booking[0].id)
            if get_minute_until_class(request, booking[0]) > 120:
                set_booking_status_single(booking[0],
                                          is_cancelled=True)
            else:
                set_booking_status_single(booking[0],
                                          is_late_cancelled=True)
        else:
            messages.error(request, f"You don't have permission to delete such item.")
    else:
        messages.error(request, f"No such booking.")
    return redirect('booking:my_class')


@login_required()
def delete_from_repeat_weekly(request, periodic_booking_id):
    periodic_booking = PeriodicBooking.objects.filter(id=periodic_booking_id)
    if periodic_booking.exists():
        if request.user == periodic_booking[0].booking_record.owner.user:
            messages.warning(request, f"{periodic_booking[0].class_name} with {periodic_booking[0].teacher} "
                                      f"at {periodic_booking[0].start_time} on "
                                      f"{to_django_weekday_name(periodic_booking[0].week_day_django)} is removed "
                                      f"from weekly booking.")
            periodic_booking[0].delete()
        else:
            messages.error(request, f"You don't have permission to modify this booking.")
    else:
        messages.error(request, f"Requested booking does not exist.")
    return redirect(reverse('booking:my_class'))


@login_required()
def delete_from_selection_schedule(request, class_id):
    # check if item exists
    if ClassDetail.objects.filter(id=class_id).exists():
        profile = Profile.objects.get(user=request.user)
        class_item = ClassDetail.objects.get(id=class_id)
        booking_record = BookingRecord.objects.get(owner=profile)
        # get item if it belongs to user
        item_to_delete = Booking.objects.filter(
            booking_record=booking_record,
            class_item=class_item,
            is_selected=True
        )
        if item_to_delete.exists():
            messages.info(request, f"{item_to_delete[0].class_item.class_name} with "
                                   f"{item_to_delete[0].class_item.teacher} has been "
                                   f"withdrawn from selection.")
            item_to_delete[0].delete()
    return redirect(reverse('schedule:schedule') + "#class_" + str(class_id))


@login_required()
def delete_from_selection_info(request, booking_id):
    item_to_delete = Booking.objects.filter(id=booking_id)
    # check if item exists
    if item_to_delete.exists():
        # check if item belongs to user
        if request.user == item_to_delete[0].booking_record.owner.user:
            messages.info(request, f"{item_to_delete[0].class_item.class_name} with "
                                   f"{item_to_delete[0].class_item.teacher} has been "
                                   f"withdrawn from selection.")
            item_to_delete[0].delete()
    return redirect('booking:my_class')


@login_required()
def delete_from_list_info(request, booking_id):
    try:
        listed_booking_to_delete = Booking.objects.get(id=booking_id)
        # check if item exists
        if request.user == listed_booking_to_delete.booking_record.owner.user:
            messages.info(request, f"{listed_booking_to_delete.class_item.class_name} with "
                                   f"{listed_booking_to_delete.class_item.teacher} has been "
                                   f"withdrawn from booking list.")
            listed_booking_to_delete.token_used = 0
            listed_booking_to_delete.save()
            set_booking_status_single(listed_booking_to_delete,
                                      is_cancelled_listed=True)
    except Exception as e:
        print(e)
    return redirect('booking:my_class')


@login_required()
def delete_from_waitlist_info(request, booking_id):
    # setup for channel
    booking_to_delete = Booking.objects.filter(id=booking_id)
    # check if item exists
    if booking_to_delete.exists():
        # check if item belongs to user
        if request.user == booking_to_delete[0].booking_record.owner.user:
            # procceed to mindbody to either withdraw from waitlist,
            # or withdraw from confirmed class (position 1, and confirmed while cancelling)
            cancel_wait_item.delay(request.user.id, booking_id)
            set_booking_status_single(booking_to_delete[0],
                                      is_cancelled=True)
    return redirect('booking:my_class')


@login_required()
def get_booking_id(request, booking_set):
    id_list = []
    try:
        for booking in booking_set:
            id_list.append(booking.id)
        return id_list
    except TypeError:
        return id_list


@login_required()
def get_minute_until_class(request, booking_item):
    try:
        if isinstance(booking_item, QuerySet):
            time_left = []
            for booking in booking_item:
                if booking.class_item.date_time_field > datetime.now():
                    time_left.append((booking.class_item.date_time_field -
                                      datetime.now()).total_seconds() / 60)
                else:
                    time_left.append(-(booking.class_item.date_time_field -
                                       datetime.now()).total_seconds() / 60)
            return time_left
        elif booking_item:
            if booking_item.class_item.date_time_field > datetime.now():
                time_left = (booking_item.class_item.date_time_field -
                             datetime.now()).total_seconds() / 60
            else:
                time_left = -(booking_item.class_item.date_time_field -
                              datetime.now()).total_seconds() / 60
            return time_left
    except AttributeError:
        return None


def get_probability(user_booking_list):
    if user_booking_list:
        probability_list = []
        for user_booking in user_booking_list:
            probability_list_single = {}
            class_capacity = user_booking.class_item.capacity
            all_user_booking_listed = Booking.objects.filter(
                class_item=user_booking.class_item, is_listed=True)
            token_spending = []
            for b in all_user_booking_listed:
                if b.token_used not in token_spending:
                    token_spending.append(b.token_used)
                token_spending.sort(reverse=True)
            ts_accumulator = 0
            for ts in token_spending:
                # if token spending is same as users booking token use,
                # then no need to + 1, if not, + 1 to get user's chance
                booking_ts = all_user_booking_listed.filter(token_used=ts).count()
                if ts == user_booking.token_used:
                    booking_ts_extra = 0
                else:
                    booking_ts_extra = 1
                if ts < user_booking.token_used:
                    probability = ((class_capacity - (ts_accumulator - 1)) /
                                   (booking_ts + booking_ts_extra))
                else:
                    probability = ((class_capacity - ts_accumulator) /
                                   (booking_ts + booking_ts_extra))
                if probability >= 1:
                    probability_list_single[ts] = "99.9%"
                elif 0.0666 < probability < 1:
                    probability_list_single[ts] = "{0:.1f}%".format(probability * 100)
                else:
                    probability_list_single[ts] = "6.7%"
                ts_accumulator += booking_ts
            probability_list.append([
                probability_list_single[int(user_booking.token_used)],
                probability_list_single
            ])
        return probability_list
    return None


def get_repeat_list_with_day(user_repeat_list):
    weekday_dict = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
                    5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
    day_repeat_list = [weekday_dict[url.week_day_django] for url in user_repeat_list]
    return zip(day_repeat_list, user_repeat_list)


@login_required()
def get_user_booked_currently(request):
    return get_user_item_opt(request,
                             is_booked_currently=True)


@login_required()
def get_user_booked_previously(request):
    return get_user_item_opt(request,
                             is_booked_previously=True)


@login_required()
def get_user_cancelled(request):
    return get_user_item_opt(request,
                             is_cancelled=True)


@login_required()
def get_user_future(request):
    return get_user_item_opt(request,
                             is_or=True,
                             is_booked_currently=True,
                             is_listed=True,
                             is_selected=True,
                             is_waitlisted=True)


@login_required()
def get_user_history_booked(request):
    return get_user_item_opt(request,
                             is_booked_previously=True, )


@login_required()
def get_user_history_all(request):
    return get_user_item_opt(request,
                             is_or=True,
                             is_booked_previously=True,
                             is_cancelled=True,
                             is_late_cancelled=True)


@login_required()
def get_user_item_opt(request, **kwargs):
    user_profile = get_object_or_404(Profile, user=request.user)
    user_booking_record = get_object_or_404(BookingRecord, owner=user_profile)
    user_booking = Booking.objects.filter(booking_record=user_booking_record)
    if kwargs.get("is_or"):
        filter_key = []
        if kwargs.get("is_cancelled"):
            filter_key.append(Q(is_cancelled='True'))
        if kwargs.get("is_cancelled_listed"):
            filter_key.append(Q(is_cancelled_listed='True'))
        if kwargs.get("is_booked_currently"):
            filter_key.append(Q(is_booked_currently='True'))
        if kwargs.get("is_late_cancelled"):
            filter_key.append(Q(is_late_cancelled='True'))
        if kwargs.get("is_listed"):
            filter_key.append(Q(is_listed='True'))
        if kwargs.get("is_booked_previously"):
            filter_key.append(Q(is_booked_previously='True'))
        if kwargs.get("is_selected"):
            filter_key.append(Q(is_selected='True'))
        if kwargs.get("is_waitlisted"):
            filter_key.append(Q(is_waitlisted='True'))
        listed_set = user_booking.filter(reduce(operator.or_, filter_key))
    else:
        listed_set = user_booking.filter(is_cancelled=kwargs.get("is_cancelled", False),
                                         is_cancelled_listed=kwargs.get("is_cancelled_listed", False),
                                         is_booked_currently=kwargs.get("is_booked_currently", False),
                                         is_late_cancelled=kwargs.get("is_late_cancelled", False),
                                         is_listed=kwargs.get("is_listed", False),
                                         is_booked_previously=kwargs.get("is_booked_previously", False),
                                         is_selected=kwargs.get("is_selected", False),
                                         is_waitlisted=kwargs.get("is_waitlisted", False))
    if listed_set.exists():
        return listed_set
    return listed_set


@login_required()
def get_user_listed(request):
    return get_user_item_opt(request, is_listed=True)


@login_required()
def get_user_repeat(request):
    profile = Profile.objects.get(user=request.user)
    booking_record = BookingRecord.objects.get(owner=profile)
    return PeriodicBooking.objects.filter(booking_record=booking_record)


@login_required()
def get_user_selected(request):
    return get_user_item_opt(request, is_selected=True)


@login_required()
def get_user_waited(request):
    return get_user_item_opt(request, is_waitlisted=True)


@login_required()
def get_user_profile(request):
    user_profile = get_object_or_404(Profile, user=request.user)
    return user_profile


@login_required()
def location_is_valid(request, user_profile, class_detail):
    # TO-DO:
    # missing:
    # ==================================================
    # The Centrium
    # Asia Standard Tower
    # The Pulse
    # World Trade Center
    # ==================================================
    # also update timetable view
    if class_detail.center_schedule.center.type == "yoga":
        if "allclubs" in user_profile.membership_type_yoga.lower():
            return True
        elif "allyoga" in user_profile.membership_type_yoga.lower():
            if not class_detail.location == "The Pulse":
                return True
        elif "cyponly" in user_profile.membership_type_yoga.lower():
            if class_detail.location == 'Grand Century Place':
                return True
        elif "mc5only" in user_profile.membership_type_yoga.lower():
            if class_detail.location == 'Millennium City 5':
                return True
        elif "linonly" in user_profile.membership_type_yoga.lower():
            if class_detail.location == 'Lincoln House':
                return True
        elif "lpyonly" in user_profile.membership_type_yoga.lower():
            if class_detail.location == 'Langham Place Office Tower':
                return True
        elif "penonly" in user_profile.membership_type_yoga.lower():
            if class_detail.location == 'Peninsula Office Tower':
                return True
        elif "pponly" in user_profile.membership_type_yoga.lower():
            if class_detail.location == 'Pacific Place':
                return True
        elif "souonly" in user_profile.membership_type_yoga.lower():
            if class_detail.location == 'Soundwill Plaza':
                return True
        elif "stsonly" in user_profile.membership_type_yoga.lower():
            if class_detail.location == 'Starstreet Precinct':
                return True
        else:
            messages.warning(request, "Your membership type is not yet supported "
                                      "by the location checking feature, please "
                                      "ensure you have access to the fitness center "
                                      "before booking, otherwise booking will be "
                                      "invalid and token will still be charged "
                                      "towards your account.")
            return True
    elif class_detail.center_schedule.center.type == "fitness":
        if "allclubs" in user_profile.membership_type_fitness.lower():
            return True
        else:
            messages.warning(request, "Your membership type is not yet supported "
                                      "by the location checking feature, please "
                                      "ensure you have access to the fitness center "
                                      "before booking, otherwise booking will be "
                                      "invalid and token will still be charged "
                                      "towards your account.")
            return True
        # elif "allfit" in user_profile.membership_type_yoga.lower():
        #     pass
    messages.error(request, f"You don't have access to "
                            f"{class_detail.location} center.")
    return False


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


def set_token_used(booking):
    if datetime.now().hour < 9:
        if int((datetime.strptime(booking.class_item.date_time_field.strftime("%Y%m%d"), "%Y%m%d") -
                datetime.strptime(datetime.today().strftime("%Y%m%d"), "%Y%m%d")).days) <= 1:
            booking.token_used = 0
            booking.save()
    else:
        if int((datetime.strptime(booking.class_item.date_time_field.strftime("%Y%m%d"), "%Y%m%d") -
                datetime.strptime(datetime.today().strftime("%Y%m%d"), "%Y%m%d")).days) <= 2:
            booking.token_used = 0
            booking.save()


def to_django_weekday(weekday):
    return (weekday.isoweekday() % 7) + 1


def to_django_weekday_name(weekday):
    weekday_dict = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday',
                    5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
    return weekday_dict[weekday]


@login_required()
def update_is_booked_status(request):
    user_profile = get_object_or_404(Profile, user=request.user)
    booking_record = BookingRecord.objects.get(owner=user_profile)
    booked_currently = Booking.objects.filter(booking_record=booking_record,
                                              is_booked_currently=True)
    if booked_currently.exists():
        for booking in booked_currently:
            if get_minute_until_class(request, booking) < 0:
                set_booking_status_single(booking,
                                          is_booked_previously=True)
    pass


@login_required()
def update_selected_unconfirmed_item(request):
    if get_user_selected(request):
        for booking in get_user_selected(request):
            if booking.class_item.date_time_field < datetime.now() + timedelta(hours=2):
                messages.info(request, "Item '" + booking.class_item.class_name + "' has been deleted")
                booking.delete()
    pass


@login_required()
def update_token_balance_status(request):
    profile = get_object_or_404(Profile, user=request.user)
    token_required = 0
    user_listed_set = get_user_listed(request)
    if user_listed_set.exists():
        for booking in user_listed_set:
            # from 00:00 to 09:00, token used count that day, and the day after
            # from 09:00 on, token used count the day after and day after tomorrow
            if datetime.now().hour < 9:
                if booking.class_item.date_time_field.strftime("%Y%m%d") == \
                        (datetime.today() + timedelta(days=2)).strftime("%Y%m%d"):
                    token_required += booking.token_used
            else:
                if booking.class_item.date_time_field.strftime("%Y%m%d") == \
                        (datetime.today() + timedelta(days=3)).strftime("%Y%m%d"):
                    token_required += booking.token_used
    if token_required > profile.token_single + 3:
        if datetime.now().hour < 9:
            messages.warning(
                request,
                f"There are not enough token left in your "
                f"account to perform all the booking(s) for "
                f"{(datetime.today() + timedelta(days=2)).strftime('%A %b %d')}"
                f", you need {str(token_required)} token(s). Please top-up your "
                f"balance before 8:00 am tomorrow to secure a mat."
            )
        else:
            messages.warning(
                request,
                f"There are not enough token left in your "
                f"account to perform all the booking(s) for "
                f"{(datetime.today() + timedelta(days=3)).strftime('%A %b %d')}"
                f", you need {str(token_required)} token(s). Please top-up your "
                f"balance before 8:00 am tomorrow to secure a mat."
            )
    pass


@login_required()
def zip_date_and_etc(request, **kwargs):
    if kwargs.get("booking_object") and kwargs.get("repeat_booking"):
        date_object = []
        rept_weekly = []
        for b_obj in kwargs.get("booking_object"):
            date_object.append(datetime.strptime(str(b_obj.class_item.center_schedule.date),
                                                 '%Y%m%d').strftime('%d %b %y, %a'))
            is_repeated = False
            for r_obj in kwargs.get("repeat_booking"):
                if b_obj.class_item.start_time == r_obj.start_time and \
                        b_obj.class_item.teacher == r_obj.teacher and \
                        b_obj.class_item.location == r_obj.location and \
                        to_django_weekday(b_obj.class_item.date_time_field) == r_obj.week_day_django:
                    rept_weekly.append(r_obj.id)
                    is_repeated = True
                    break
            if not is_repeated:
                rept_weekly.append("")
        if kwargs.get("bt_forms"):
            return zip(date_object, kwargs.get("booking_object"), rept_weekly,
                       kwargs.get("bt_forms"), kwargs.get("probability"))
        return zip(date_object, kwargs.get("booking_object"), rept_weekly)
    elif kwargs.get("booking_object"):
        date_object = []
        rept_weekly = []
        for b_obj in kwargs.get("booking_object"):
            date_object.append(datetime.strptime(str(b_obj.class_item.center_schedule.date),
                                                 '%Y%m%d').strftime('%d %b %y, %a'))
            rept_weekly.append("")
        if kwargs.get("bt_forms"):
            return zip(date_object, kwargs.get("booking_object"), rept_weekly,
                       kwargs.get("bt_forms"), kwargs.get("probability"))
        return zip(date_object, kwargs.get("booking_object"))
    return None


@login_required()
def my_history(request):
    user_history_set = zip_date_and_etc(
        request,
        booking_object=get_user_history_all(request).order_by('-class_item__date_time_field'),
    )
    content = {
        'date_today': datetime.today().strftime('%d %b %Y, %a'),
        'history_set': user_history_set,
    }
    return render(request, 'booking/history.html', content)


class MyClass(View):
    template = 'booking/class.html'

    # display blank form
    def get(self, request):
        bookings = get_user_listed(request).order_by("class_item__date_time_field")
        bookings_free, bookings_token = [], []
        for booking in bookings:
            if datetime.now().hour < 9:
                if (booking.class_item.date_time_field - datetime.now()).days >= 2:
                    bookings_token.append(booking)
                else:
                    bookings_free.append(booking)
            else:
                if (booking.class_item.date_time_field - datetime.now()).days >= 3:
                    bookings_token.append(booking)
                else:
                    bookings_free.append(booking)
        bt_forms = [
            BookingTokenForm(initial={'token_used': booking_token.token_used}, prefix=str(x), instance=Booking())
            for x, booking_token in zip(range(0, len(bookings_token)), bookings_token)]
        content = self.get_content(request, bt_forms, bookings_free, bookings_token)
        if get_user_selected(request):
            user_selected_amount = get_user_selected(request).count()
            content.update({'user_selected_amount': user_selected_amount})
        return render(request, self.template, content)

    # process form data
    def post(self, request):
        profile = Profile.objects.get(user=request.user)
        bookings = get_user_listed(request).order_by("class_item__date_time_field")
        bookings_free, bookings_token = [], []
        for booking in bookings:
            if datetime.now().hour < 9:
                if booking.class_item.date_time_field.day - datetime.now().day >= 2:
                    bookings_token.append(booking)
                else:
                    bookings_free.append(booking)
            else:
                if booking.class_item.date_time_field.day - datetime.now().day >= 3:
                    bookings_token.append(booking)
                else:
                    bookings_free.append(booking)
        bt_forms = [BookingTokenForm(request.POST, prefix=str(x), instance=Booking())
                    for x in range(0, len(bookings_token))]
        if all([bt_f.is_valid() for bt_f in bt_forms]):
            for bt_f, booking_token in zip(bt_forms, bookings_token):
                # min. 1 token required for classes listed 3 days in advance
                if bt_f.cleaned_data['token_used'] > 0:
                    if (profile.get_token_needed() - booking_token.token_used) \
                            + bt_f.cleaned_data['token_used'] <= profile.token_single:
                        if booking_token.token_used != bt_f.cleaned_data['token_used']:
                            messages.info(request,
                                          f"Updated {booking_token.class_item.date_time_field.strftime('%d %b %y, %a')} "
                                          f"{booking_token.class_item.class_name} token spending from "
                                          f"{booking_token.token_used} to {bt_f.cleaned_data['token_used']}")
                            booking_token.token_used = bt_f.cleaned_data['token_used']
                            booking_token.save()
                    else:
                        messages.error(request,
                                       f"Thre is not sufficient amount of token to increase spending to "
                                       f"{bt_f.cleaned_data['token_used']} for {booking_token.class_item.class_name} "
                                       f"on {booking_token.class_item.date_time_field.strftime('%d %b %y, %a')}")
                else:
                    messages.error(request, f"Minimum 1 token is require to list {booking_token.class_item.class_name} "
                                            f"on {booking_token.class_item.date_time_field.strftime('%d %b %y, %a')}")

        bt_forms = [
            BookingTokenForm(initial={'token_used': booking_token.token_used}, prefix=str(x), instance=Booking())
            for x, booking_token in zip(range(0, len(bookings_token)), bookings_token)]
        content = self.get_content(request, bt_forms, bookings_free, bookings_token)
        if get_user_selected(request):
            user_selected_amount = get_user_selected(request).count()
            content.update({'user_selected_amount': user_selected_amount})
        return render(request, self.template, content)

    # return all necessary content for rendering page
    def get_content(self, request, bt_forms, bookings_free, bookings_token):
        update_token_balance_status(request)
        update_user_waitlist.delay(request.user.id)
        # to run update_user_schedule() within update_user_waitlst() to avoid
        # adding waitlisted class before update_user_waitlist() is done checking
        # update_user_schedule.delay(request.user.id)
        user_booked = get_user_booked_currently(request)
        user_confirmed_id = get_booking_id(request, user_booked)
        if user_booked.exists():
            user_booked_time = get_minute_until_class(request, user_booked)
        else:
            user_booked_time = 0
        if user_confirmed_id:
            cancel_confirmed = zip(user_confirmed_id, user_booked, user_booked_time)
        else:
            cancel_confirmed = None
        user_waited = get_user_waited(request)
        cancel_wait_list = zip(get_booking_id(request, user_waited), user_waited)
        user_listed = get_user_listed(request)
        cancel_listed = zip(get_booking_id(request, user_listed), user_listed)
        user_future = get_user_future(request)
        future_list = zip(get_booking_id(request, user_future), user_future)
        user_repeat = get_user_repeat(request)
        repeat_list = zip(get_booking_id(request, user_repeat), user_repeat)
        user_profile = get_user_profile(request)
        user_repeat_list = get_user_repeat(request)
        user_booked_list = zip_date_and_etc(
            request,
            booking_object=get_user_booked_currently(request).order_by('class_item__date_time_field'),
            repeat_booking=user_repeat_list,
        )
        user_waited_list = zip_date_and_etc(
            request,
            booking_object=get_user_waited(request).order_by('class_item__date_time_field'),
            repeat_booking=user_repeat_list,
        )
        user_listed_list_free = zip_date_and_etc(
            request,
            booking_object=bookings_free,
            repeat_booking=user_repeat_list,
        )
        user_listed_list_token = zip_date_and_etc(
            request,
            booking_object=bookings_token,
            repeat_booking=user_repeat_list,
            bt_forms=bt_forms,
            probability=get_probability(bookings_token),
        )
        user_selected_list = zip_date_and_etc(
            request,
            booking_object=get_user_selected(request).order_by('class_item__date_time_field'),
        )
        if user_repeat_list:
            user_repeat_list_with_day = get_repeat_list_with_day(user_repeat_list.order_by('week_day_django', 'start_time'))
        else:
            user_repeat_list_with_day = []
        # with 20+ items only displays 20 items in info
        if get_user_history_booked(request).exists():
            user_history_list = zip_date_and_etc(
                request,
                booking_object=get_user_history_booked(request).order_by('-class_item__date_time_field')[:20],
            )
        else:
            user_history_list = zip_date_and_etc(
                request,
                booking_object=get_user_history_booked(request).order_by('-class_item__date_time_field'),
            )
        return {
            'date_today': datetime.today(),
            'user_profile': user_profile,
            'booked_list': user_booked_list,
            'cancel_confirmed': cancel_confirmed,
            'cancel_wait_list': cancel_wait_list,
            'cancel_listed': cancel_listed,
            'waited_list': user_waited_list,
            'listed_list_token': user_listed_list_token,
            'listed_list_free': user_listed_list_free,
            'selected_list': user_selected_list,
            'weekly_list': user_repeat_list_with_day,
            'history_list': user_history_list,
            'future_list': future_list,
            'repeat_list': repeat_list,
        }
