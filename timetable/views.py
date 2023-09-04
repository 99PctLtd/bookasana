from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .models import Center, CenterSchedule, ClassDetail
from account.models import Profile
from booking import views as tool
from booking.book_class import update_user_waitlist
from booking.models import Booking, BookingRecord
from booking.views import get_user_waited, update_token_balance_status
from account.models import Profile

from datetime import datetime, timedelta, date


def class_before_eleven(class_list):
    class_id_return = []
    if datetime.now().hour < 11:
        for class_single in class_list[0]:
            if class_single.date_time_field.time() <= datetime.strptime("11:00 am", '%I:%M %p').time():
                class_id_return.append(class_single.id)
    elif datetime.now().hour >= 23:
        for class_single in class_list[1]:
            if class_single.date_time_field.time() <= datetime.strptime("11:00 am", '%I:%M %p').time():
                class_id_return.append(class_single.id)
    return class_id_return


def class_in_past(class_list):
    class_id_return = []
    for class_single in class_list[0]:
        if class_single.date_time_field < datetime.now():
            class_id_return.append(class_single.id)
    return class_id_return


def class_in_two(class_list):
    class_id_return = []
    for class_single in class_list[0]:
        if class_single.date_time_field < datetime.now() + timedelta(hours=2):
            class_id_return.append(class_single.id)
    return class_id_return


def get_next_class_id(center_schedule):
    # return class_id of next available class for booking
    class_detail = ClassDetail.objects.filter(center_schedule=center_schedule)
    if class_detail.order_by('date_time_field').last().date_time_field - timedelta(hours=2) > datetime.now():
        # when there are class available for booking
        next_class = class_detail.order_by('date_time_field').last()
        for class_single in class_detail:
            if class_single.date_time_field - timedelta(hours=2) > datetime.now():
                if class_single.date_time_field < next_class.date_time_field:
                    next_class = class_single
    else:
        # when time exceed last class of today, return class from tomorrow
        center_schedule_tmr = CenterSchedule.objects.get(date=str((datetime.today() +
                                                                   timedelta(days=1)).strftime("%Y%m%d")))
        class_detail = ClassDetail.objects.filter(center_schedule=center_schedule_tmr).order_by('date_time_field')
        next_class = class_detail.first()
    class_in_future = class_detail.filter(start_time=next_class.start_time)
    class_id = class_in_future.order_by('date_time_field').first().id
    return class_id


def get_user_center(request):
    user = request.user
    user_profile = Profile.objects.get(user=user)

    # TO-DO:
    # missing:
    # ==================================================
    # The Centrium
    # Asia Standard Tower
    # The Pulse
    # Lincoln House
    # World Trade Center
    # ==================================================
    # also update booking : location_validation
    if user_profile.membership_ref_yoga:
        if "allclubs" in user_profile.membership_type_yoga.lower():
            return ""
        elif "allyoga" in user_profile.membership_type_yoga.lower():
            return ""
        elif "cyponly" in user_profile.membership_type_yoga.lower():
            return 'grand century, '
        elif "linonly" in user_profile.membership_type_yoga.lower():
            return 'lincoln, '
        elif "lpyonly" in user_profile.membership_type_yoga.lower():
            return 'langham, '
        elif "mc5only" in user_profile.membership_type_yoga.lower():
            return 'millennium, '
        elif "penonly" in user_profile.membership_type_yoga.lower():
            return 'peninsula, '
        elif "pponly" in user_profile.membership_type_yoga.lower():
            return 'pacific place, '
        elif "souonly" in user_profile.membership_type_yoga.lower():
            return 'soundwill'
        elif "stsonly" in user_profile.membership_type_yoga.lower():
            return 'starstreet'
        else:
            return ""
    else:
        return ""


def class_audio(week_class_details):
    class_id_return = []
    for day_class_detail in week_class_details:
        for class_detail in day_class_detail:
            if "guided audio meditation".lower() in class_detail.class_name.lower():
                class_id_return.append(class_detail.id)
    return class_id_return


@login_required()
def get_user_booking_content(request, class_list, week_class_details):
    user_booked, user_waited, user_listed, user_selected = [], [], [], []
    current_ids = tool.get_user_booked_currently(request)
    waited_ids = tool.get_user_waited(request)
    listed_ids = tool.get_user_listed(request)
    selected_ids = tool.get_user_selected(request)
    if current_ids:
        for x in current_ids:
            user_booked.append(x.class_item.id)
    if waited_ids:
        for x in waited_ids:
            user_waited.append(x.class_item.id)
    if listed_ids:
        for x in listed_ids:
            user_listed.append(x.class_item.id)
    if selected_ids:
        for x in selected_ids:
            user_selected.append(x.class_item.id)

    # update waitlist position
    user_waitlist_set = get_user_waited(request)
    if user_waitlist_set.exists():
        update_user_waitlist(request.user.id)

    profile = Profile.objects.get(user=request.user)
    booking_record = BookingRecord.objects.get(owner=profile)
    user_waited_items_set = Booking.objects.filter(
        booking_record=booking_record,
        is_waitlisted=True
    )
    user_center = get_user_center(request)
    return {
        'class_audio': class_audio(week_class_details),
        'class_in_past': class_in_past(week_class_details),
        'class_in_two': class_in_two(week_class_details),
        'class_before_nine': class_before_eleven(week_class_details),
        'class_list': class_list,
        'user_booked': user_booked,
        'user_waited': user_waited,
        'user_waited_items_set': user_waited_items_set,
        'user_listed': user_listed,
        'user_selected': user_selected,
        'user_selected_amount': len(user_selected),
        'user_center': user_center,
    }


def schedule_current(request):
    center_schedule = CenterSchedule.objects.filter(date=str(datetime.today().strftime("%Y%m%d")))
    if center_schedule.exists():
        next_id = get_next_class_id(center_schedule[0])
        if not next_id:
            next_id = ClassDetail.objects.filter(center_schedule=center_schedule).order_by('date_time_field').first().id
        return redirect(reverse('schedule:schedule') + "#class_" + str(next_id))
    return redirect(reverse('schedule:schedule'))


def schedule(request):
    class_list =[]
    week_class_details = []
    week_dates = []
    # 00000000 reserved for schedule update check
    if CenterSchedule.objects.exists():
        date_difference = (datetime.strptime(CenterSchedule.objects.all().order_by('-date').first().date, '%Y%m%d') - datetime.today()).days + 2
        if date_difference >= 2:
            for i in range(0, date_difference):
                week_dates.append([(date.today() + timedelta(days=i)).strftime('%d %B %Y, %A'),
                                  (date.today() + timedelta(days=i)).strftime('%d %B, %A')])
                day_center_schedule = get_object_or_404(CenterSchedule, date=str((date.today() + timedelta(days=i)).strftime("%Y%m%d")))
                day_class_detail = ClassDetail.objects.filter(center_schedule=day_center_schedule)
                week_class_details.append(day_class_detail.order_by("date_time_field"))

            class_list = zip(week_dates, week_class_details)
            if request.user.is_authenticated:
                content = get_user_booking_content(request, class_list, week_class_details)
                return render(request, 'timetable/schedule.html', content)
            return render(request,
                          'timetable/schedule.html',
                          {
                              'class_in_past': class_in_past(week_class_details),
                              'class_list': class_list,
                          })
    return render(request,
                  'timetable/schedule.html',
                  {'class_list': class_list})
