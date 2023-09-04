import operator
from functools import reduce
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404

import requests
import json
from asgiref.sync import async_to_sync
from celery import shared_task
from channels.layers import get_channel_layer
from bs4 import BeautifulSoup
from datetime import datetime

from authentication.models import User
from account.models import Profile, CookieJar, Cookie
from booking.models import Booking, BookingRecord
from timetable.models import ClassDetail


@login_required()
def book_single(request, booking):
    # get cookies | extracted from cookie_setting
    client_session = requests.Session()
    client_session, cookie_jar = cookie_setting(request.user.id, client_session)
    # setup for channel
    user = request.user
    group_name = user.username
    channel_layer = get_channel_layer()
    # book selected class
    user = request.user
    profile = Profile.objects.get(user=user)
    booking_url = get_studio_links(booking.class_item.location)
    class_id = booking.class_item.class_id
    class_date = booking.class_item.date_time_field.date().strftime('%-m/%-d/%Y')
    membership_ref = profile.membership_ref_yoga
    response = client_session.get(
        booking_url[0] + class_id +
        booking_url[1] + class_date +
        booking_url[2] + membership_ref +
        booking_url[3], headers=get_headers(),
    )
    # check booking status
    soup = BeautifulSoup(response.content, "lxml")
    if soup.find("input", {"name": "AddWLButton"}):
        # waitlist: booking directly, return waitlist position
        data_waitlist = {
            'CSRFToken': cookie_jar.cookie_csrf,
            'frmClassID': class_id,
            'frmClassDate': class_date,
        }
        # response redirect to https://clients.mindbodyonline.com/ASP/my_waitlist.asp
        # possible to get all waitlist item positions
        response = client_session.post('https://clients.mindbodyonline.com/ASP/waitlist_a.asp',
                                       headers=get_headers(), data=data_waitlist)
        # update is_waitlisted items' waitlist postions
        soup = BeautifulSoup(response.content, "lxml")
        class_schedule = soup.find("table", {"class": "myInfoTable"})
        table_schedule = get_table(class_schedule)
        update_single_waitlist(table_schedule, booking)
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': f"{booking.class_item.class_name} is currently full. "
                               f"You are positioned {booking.waitlist_position} "
                               f"on the waitlist.",
                    'level': "warning",
                }
            }
        )
        messages.warning(request, f"{booking.class_item.class_name} is currently full. "
                                  f"You are positioned {booking.waitlist_position} "
                                  f"on the waitlist.")
        client_session.close()
        return True
    elif soup.find("td", {"class": "mainText center-ch"}):
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': f"{booking.class_item.class_name} with "
                               f"{booking.class_item.teacher} at "
                               f"{booking.class_item.start_time} is full, "
                               f"wait list is also full.",
                    'level': "error",
                }
            }
        )
        messages.error(request, f"{booking.class_item.class_name} with "
                                f"{booking.class_item.teacher} at "
                                f"{booking.class_item.start_time} is full, "
                                f"wait list is also full.")
        client_session.close()
        return False
    elif soup.find("div", {"class": "section"}):
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': f"Unable to add {booking.class_item.class_name} with "
                               f"{booking.class_item.teacher} to schedule, you are "
                               f"already scheduled at this time.",
                    'level': "error",
                }
            }
        )
        messages.error(request, f"Unable to add {booking.class_item.class_name} with "
                                f"{booking.class_item.teacher} to schedule, you are "
                                f"already scheduled at this time.")
        client_session.close()
        return False
    elif soup.find("div", {"class": "error-content"}) and soup.find("img", {"class": "error-art"}):
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': f"There were some technical difficulties, we couldn't add "
                               f"{booking.class_item.class_name} to schedule, please "
                               f"try booking this class again.",
                    'level': "error",
                }
            }
        )
        messages.error(request, f"There were some technical difficulties, we couldn't add "
                                f"{booking.class_item.class_name} to schedule, please "
                                f"try booking this class again.")
        cookie_jar.delete()
        client_session.close()
        return False
    else:
        # booking successful
        response = client_session.post('https://clients.mindbodyonline.com/ASP/my_sch.asp',
                                       headers=get_headers())
        soup = BeautifulSoup(response.content, "lxml")
        class_schedule = soup.find("table", {"class": "myInfoTable"})
        table_schedule = get_table(class_schedule)
        update_single_schedule(table_schedule, booking)
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': f"{booking.class_item.class_name} with "
                               f"{booking.class_item.teacher} is booked!",
                    'level': "success",
                }
            }
        )
        messages.success(request, f"{booking.class_item.class_name} with "
                                  f"{booking.class_item.teacher} is booked!")
        client_session.close()
        return True


@shared_task()
def cancel_single(user_id, booking_id):
    user = User.objects.get(id=user_id)
    booking = Booking.objects.get(id=booking_id)
    request_url = [
        "https://clients.mindbodyonline.com/ASP/adm/adm_res_canc.asp?visitID=",
        "&cType=",
    ]
    # setup for channel
    group_name = user.username
    channel_layer = get_channel_layer()
    # get cookies | extracted to cookie_setting
    client_session = requests.Session()
    client_session, cookie_jar = cookie_setting(user.id, client_session)
    if cookie_jar is not None:
        # cancel class
        visit_id = booking.visit_id
        # normal cancel type=1
        # late cancel   type=2
        if (booking.class_item.date_time_field - datetime.now()).total_seconds() / 60 > 120:
            client_session.get(
                request_url[0] + visit_id + request_url[1] + "1",
                headers=get_headers(),
            )
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'text': {
                        'message': f"{booking.class_item.class_name} on "
                                   f"{booking.class_item.date_time_field.date()} at "
                                   f"{booking.class_item.start_time} is cancelled.",
                        'level': "warning",
                    }
                }
            )
        else:
            client_session.get(
                request_url[0] + visit_id + request_url[1] + "2",
                headers=get_headers(),
            )
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'text': {
                        'message': f"{booking.class_item.class_name} on "
                                   f"{booking.class_item.date_time_field.date()} at "
                                   f"{booking.class_item.start_time} is cancelled late.",
                        'level': "error",
                    }
                }
            )
    else:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': "Invalid login account/password, please check and try again.",
                    'level': "error",
                }
            }
        )
    client_session.close()


@shared_task()
def cancel_wait_item(user_id, booking_id):
    # setup for channel
    user = User.objects.get(id=user_id)
    group_name = user.username
    channel_layer = get_channel_layer()
    booking = Booking.objects.get(id=booking_id)
    request_url = "https://clients.mindbodyonline.com/ASP/my_waitlist.asp"
    # get cookies | extracted to cookie_setting
    client_session = requests.Session()
    client_session, cookie_jar = cookie_setting(user_id, client_session)
    if cookie_jar is not None:
        # cancel class
        class_id = booking.class_item.class_id
        class_date = booking.class_item.date_time_field.date().strftime('%-m/%-d/%Y')
        data_waitlist = {
            'CSRFToken': cookie_jar.cookie_csrf,
            'frmClassID': class_id,
            'frmClassDate': class_date,
            'frmDelWaitList': "true",
        }
        response = client_session.post(
            request_url,
            headers=get_headers(),
            data=data_waitlist,
        )
        # soup = BeautifulSoup(response.content, "lxml")
        # class_schedule = soup.find("table", {"class": "myInfoTable"})

        # TO-DO : in case cancel after class is confirmed
        # check if myInfoTable exists
        # ==========
        # if class_schedule:
        #     table_schedule = get_table(class_schedule)
        #     if booking.waitlist_position > 3:
        #         client_session.close()
        #     else:
        #         # to check schedule list to see if item exists
        #         client_session.close()
        # # if not, it means there is not waitlist items
        # else:
        #     client_session.close()
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': f"{booking.class_item.class_name} with "
                               f"{booking.class_item.teacher} has been "
                               f"withdrawn from wait list.",
                    'level': "info",
                }
            }
        )
        # booking.delete()
    else:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'text': {
                    'message': "Invalid login account/password, "
                               "please check and try again.",
                    'level': "error",
                }
            }
        )
    client_session.close()


def check_from_wait_to_schedule(client_session, booking_wait_set, group_name):
    # setup for channel
    channel_layer = get_channel_layer()
    response_check = client_session.get('https://clients.mindbodyonline.com/ASP/my_sch.asp',
                                        headers=get_headers())
    soup_check = BeautifulSoup(response_check.content, "lxml")
    class_schedule_check = soup_check.find("table", {"class": "myInfoTable"})
    if class_schedule_check:
        table_schedule_check = get_table(class_schedule_check)
        for booking in booking_wait_set:
            wait_item_is_cancelled = True
            for item in table_schedule_check:
                if item[1] == booking.class_item.start_time and \
                        booking.class_item.class_name in item[2] and \
                        item[3] == booking.class_item.teacher and \
                        item[4] == booking.class_item.location:
                    wait_item_is_cancelled = False
                    if booking.class_item.class_name in item[2]:
                        set_booking_status_single(booking,
                                                  is_booked_currently=True)
                        booking.visit_id = item[7][:9]
                        booking.save()
                        # messages.success(request,
                        #                  booking.class_item.class_name +
                        #                  " confirmed from wait list.")
                        async_to_sync(channel_layer.group_send)(
                            group_name,
                            {
                                'type': 'send_notification',
                                'text': {
                                    'message': f"{booking.class_item.class_name} with "
                                               f"{booking.class_item.teacher} at "
                                               f"{booking.class_item.start_time} is "
                                               f"confirmed from wait list.",
                                    'level': "success",
                                }
                            }
                        )
            # item is already missing in wait list
            # proceed to delete if also missing in schedule
            if wait_item_is_cancelled:
                # messages.info(request, "user canceled " + booking.class_item.class_name +
                #               " from Pure wait list, bookasana sync to match schedule.")
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'send_notification',
                        'text': {
                            'message': f"User canceled {booking.class_item.class_name} "
                                       f"from Pure wait list, bookasana sync to match schedule.",
                            'level': "warning",
                        }
                    }
                )
                booking.delete()


# TO-DO:
# ==================================================
# 1. how to address invalid login account or password???
#
# extracted from book_single, need testing to check
def cookie_setting(user_id, client_session):
    user = User.objects.get(id=user_id)
    profile = Profile.objects.get(user=user)
    cookie_jar, is_created = CookieJar.objects.get_or_create(profile=profile)
    data_login = {
        'requiredtxtUserName': user.pure_login,
        'requiredtxtPassword': user.pure_password,
    }

    # setup for channel
    group_name = user.username
    channel_layer = get_channel_layer()

    # print(f"{(datetime.now() - cookie_jar.date_time_field).total_seconds() / 60} min")
    if is_created or (datetime.now() - cookie_jar.date_time_field).total_seconds() / 60 >= 30:
        # scrape new cookies if db cookies is older than 30 minutes
        for x in range(3):
            client_session.get(get_schedule_url(), headers=get_headers())
        response = client_session.post("https://clients.mindbodyonline.com/Login?"
                                       "studioID=81&isLibAsync=true&isJson=true",
                                       headers=get_headers(), data=data_login)
        # if login success
        if json.loads(response.text)['json']['success']:
            dict_cookies = client_session.cookies.get_dict()
            # delete all previous cookies
            cookie = Cookie.objects.filter(cookie_jar=cookie_jar)
            if cookie.exists():
                for c in cookie:
                    c.delete()
            # create new cookies
            for c in dict_cookies:
                cookie_jar.cookie_set.create(
                    cookie_jar=cookie_jar,
                    cookie_name=c,
                    cookie_value=dict_cookies[c]
                )
            # set csrf
            response = client_session.get(
                'https://clients.mindbodyonline.com/ASP/my_ph.asp',
                headers=get_headers(),
            )
            soup = BeautifulSoup(response.content, "lxml")
            cookie_jar.cookie_csrf = soup.find("input", {"name": "CSRFToken"}).get('value')
            cookie_jar.save()
        else:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'text': {
                        'message': f"Login error: We encounter technical issue logging into "
                                   f"your account, please check if you have the correct "
                                   f"login name and password and try again.",
                        'level': "error",
                    }
                }
            )
            cookie_jar.delete()
            return client_session, None
    else:
        [client_session.cookies.set(c.cookie_name, c.cookie_value) for c in
         Cookie.objects.filter(cookie_jar=cookie_jar)]
        update_cookie_jar_time(cookie_jar)
    return client_session, cookie_jar


def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0',
    }


def get_schedule_url(date=datetime.today().strftime('%Y%m%d')):
    try:
        return "https://clients.mindbodyonline.com/classic/mainclass?studioid=81" \
               "&tg=&vt=&lvl=&stype=&view=&trn=0&page=&catid=&prodid=&date=" + \
               date[4:6] + "%2f" + date[6:] + "%2f" + date[:4] + "&classid=0&prodGroupId=&" \
                                                                 "sSU=&optForwardingLink=&qParam=&justloggedin=&nLgIn=&pMode=0"
    except TypeError:
        print('TypeError: date has to be an integer.')


# should return only the link for one studio
def get_studio_links(location):
    # class_id_num, booking_date, membership_ref_yoga to be fill inbetween
    if location == 'The Centrium':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=1&typeGroupID=2&recurring=false&wlID="]
    elif location == 'Soundwill Plaza':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=3&typeGroupID=23&recurring=false&wlID="]
    elif location == 'Peninsula Office Tower':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=7&typeGroupID=41&recurring=false&wlID="]
    elif location == 'Langham Place Office Tower':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=10&typeGroupID=24&recurring=false&wlID="]
    elif location == 'Lincoln House':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=14&typeGroupID=27&recurring=false&wlID="]
    elif location == 'Asia Standard Tower':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=16&typeGroupID=22&recurring=false&wlID="]
    elif location == 'The Pulse':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=22&typeGroupID=65&recurring=false&wlID="]
    elif location == 'Hutchison House':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=24&typeGroupID=67&recurring=false&wlID="]
    elif location == 'Pacific Place':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=26&typeGroupID=72&recurring=false&wlID="]
    elif location == 'World Trade Centre':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=27&typeGroupID=23&recurring=false&wlID="]
    elif location == 'Grand Century Place':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=28&typeGroupID=24&recurring=false&wlID="]
    elif location == 'Millennium City 5':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=29&typeGroupID=74&recurring=false&wlID="]
    elif location == 'Starstreet Precinct':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=30&typeGroupID=72&recurring=false&wlID="]
    else:
        print('new center to be add...')
    return None


def get_table(class_schedule):
    # parse schedule to list
    table_schedule = []
    for row in class_schedule.find_all('tr'):
        if row.find(id='startTimeHeader') is None:
            row_temp = []
            column_marker = 0
            columns = row.find_all('td')
            for column in columns:
                if column_marker == 1:
                    if column.find("input", {'class': "SignupButton"}) is None:
                        row_temp.append(column.get_text())
                        column_marker += 1
                    else:
                        row_temp.append(column.find("input", {'class': "SignupButton"}).attrs['name'][3:])
                        column_marker += 1
                elif column_marker == len(row.find_all('td')) - 1:
                    if column.get_text() == "Cancel" or column.get_text() == "Late Cancel":
                        row_temp.append(column.find('a').attrs['href'][21:30] + "," +
                                        column.find('a').attrs['href'][-2:-1])
                    else:
                        row_temp.append(column.get_text())
                else:
                    row_temp.append(column.get_text())
                    column_marker += 1
            table_schedule.append(row_temp)
    # deleting non table rows
    # on schedule page, if no booking, it says 'No Schedule Sessions'
    table_schedule[:] = [ts for ts in table_schedule if len(ts) > 1]
    # clean up data
    for row in table_schedule:
        # remove \xa0 from start time
        row[1] = row[1].replace(u' ', u'')
        row[1] = row[1].replace(u'\xa0', u' ')
        row[1] = datetime.strptime(row[1], '%I:%M %p').strftime('%H:%M')
        # replace \n\n from cancel
        row[7] = row[7].replace(u'\n\n', u'')
        # remove \xa0 from class name
        row[2] = row[2].replace(u'\xa0', u' ')
        # remove \xa0 from location
        row[4] = row[4].replace(u'\xa0', u' ')
        # remove \xa0 from location
        row[6] = row[6].replace(u'\xa0', u' ')
        # remove Yoga -
        if row[4] == 'Pure South - The Pulse':
            row[4] = row[4].replace(u'Pure South - ', u'')
        else:
            row[4] = row[4].replace(u'Yoga - ', u'')
    return table_schedule


@login_required()
def get_user_item_opt(request, **kwargs):
    user_profile = get_object_or_404(Profile, user=request.user)
    user_booking_record = get_object_or_404(BookingRecord, owner=user_profile)
    user_booking = Booking.objects.filter(booking_record=user_booking_record)
    if kwargs.get("is_or"):
        filter_key = []
        if kwargs.get("is_cancelled"):
            filter_key.append(Q(is_cancelled='True'))
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
                                         is_booked_currently=kwargs.get("is_booked_currently", False),
                                         is_late_cancelled=kwargs.get("is_late_cancelled", False),
                                         is_listed=kwargs.get("is_listed", False),
                                         is_booked_previously=kwargs.get("is_booked_previously", False),
                                         is_selected=kwargs.get("is_selected", False),
                                         is_waitlisted=kwargs.get("is_waitlisted", False))
    if listed_set.exists():
        return listed_set
    return listed_set


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


def update_cookie_jar_time(cookie_jar):
    cookie_jar.date_time_field = datetime.now()
    cookie_jar.save()


def update_single_schedule(table_schedule, booking):
    # pass in clean up table_schedule list
    # update bookings waitlist position with is_waitlisted status
    for item in table_schedule:
        # item[2] may include (From Wait List - Confirmed.)
        if item[1] == booking.class_item.start_time and \
                booking.class_item.class_name in item[2] and \
                item[3] == booking.class_item.teacher and \
                item[4] == booking.class_item.location:
            booking.visit_id = item[7][:9]
            booking.save()
            break


@shared_task()
def update_user_schedule(user_id):
    # check if any change to is_currently_booked and is_waitlisted items
    # confirm from wait list : (From Wait List - Confirmed.)
    refresh_min = 15
    user = User.objects.get(id=user_id)
    profile = Profile.objects.get(user=user)
    booking_record = BookingRecord.objects.get(owner=profile)
    booking_current_set = Booking.objects.filter(
        booking_record=booking_record,
        is_booked_currently=True,
    )
    # setup for channel
    group_name = user.username
    channel_layer = get_channel_layer()
    # prevent checking mindbody schedule everytime user refreshes
    # only check if the last check has been older than 15 mins
    if (datetime.now() - booking_record.schedule_update_time).total_seconds() / 60 > refresh_min:
        booking_record.schedule_update_time = datetime.now()
        booking_record.save()
        client_session = requests.Session()
        client_session, cookie_jar = cookie_setting(user_id, client_session)
        if cookie_jar is not None:
            response = client_session.get('https://clients.mindbodyonline.com/ASP/my_sch.asp',
                                          headers=get_headers())
            soup = BeautifulSoup(response.content, "lxml")
            class_schedule = soup.find("table", {"class": "myInfoTable"})
            if class_schedule:
                table_schedule = get_table(class_schedule)
                if booking_current_set.exists():
                    for booking in booking_current_set:
                        check_point = True
                        for item in table_schedule:
                            # check if schedule item exists in booking
                            if item[1] == booking.class_item.start_time and \
                                    booking.class_item.class_name in item[2] and \
                                    item[3] == booking.class_item.teacher and \
                                    item[4] == booking.class_item.location:
                                # check if such item is on wait list
                                # since it first update user waitlist
                                # therefore, here we shall never have to set to current
                                if booking.class_item.class_name in item[2] and \
                                        booking.is_waitlisted:
                                    set_booking_status_single(booking,
                                                              is_booked_currently=True)
                                check_point = False
                                break
                        # if pass, meaning booking item is not in schedule table,
                        # meaning user deleted that item from mindbody therefore, can be deleted
                        if check_point:
                            set_booking_status_single(booking,
                                                      is_cancelled=True)
                            async_to_sync(channel_layer.group_send)(
                                group_name,
                                {
                                    'type': 'send_notification',
                                    'text': {
                                        'message': f"User canceled {booking.class_item.class_name} "
                                                   f"from Pure, bookasana sync to match schedule.",
                                        'level': "warning",
                                    }
                                }
                            )
                if booking_current_set.count() != len(table_schedule):
                    # item exists in schedule table but missing in booking
                    # meaning client booked from mindbody, not bookasana
                    for item in table_schedule:
                        class_item = ClassDetail.objects.get(
                            start_time=item[1],
                            teacher=item[3],
                            location=item[4],
                            date_time_field=datetime.strptime(item[0] + " " + item[1], '%a %d/%m/%Y %H:%M')
                        )
                        booking, is_created = Booking.objects.get_or_create(
                            booking_record=booking_record,
                            class_item=class_item,
                            is_booked_currently=True,
                        )
                        if is_created:
                            booking.token_used = 0
                            booking.save()
                            update_single_schedule(table_schedule, booking)
                            async_to_sync(channel_layer.group_send)(
                                group_name,
                                {
                                    'type': 'send_notification',
                                    'text': {
                                        'message': "User added " + booking.class_item.class_name +
                                                   " to Pure schedule, bookasana sync to match schedule.",
                                        'level': "success",
                                    }
                                }
                            )
        else:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'text': {
                        'message': "Invalid login account/password, please check and try again.",
                        'level': "error",
                    }
                }
            )
        client_session.close()


def update_single_waitlist(table_schedule, booking):
    # pass in clean up table_schedule list
    # update bookings waitlist position with is_waitlisted status
    for item in table_schedule:
        if item[1] == booking.class_item.start_time and \
                item[2] == booking.class_item.class_name and \
                item[3] == booking.class_item.teacher and \
                item[4] == booking.class_item.location:
            booking.waitlist_position = int(item[6])
            booking.save()


@shared_task()
def update_user_waitlist(user_id):
    refresh_min = 15
    user = User.objects.get(id=user_id)
    profile = Profile.objects.get(user=user)
    booking_record = BookingRecord.objects.get(owner=profile)
    booking_wait_set = Booking.objects.filter(
        booking_record=booking_record,
        is_waitlisted=True
    )
    # setup for channel
    group_name = user.username
    channel_layer = get_channel_layer()
    # to prevent checking mindbody wait list everytime user refreshes
    # default set to refresh every 15 minutes, only if there is a wait list class
    # starting in 2hr, should it fresh every 1 min 10 minutes before closing,
    for booking in booking_wait_set:
        if (booking.class_item.date_time_field - datetime.now()).total_seconds() / 60 - 120 < 10:
            refresh_min = 1
            break
    if (datetime.now() - booking_record.waitlist_update_time).total_seconds() / 60 > refresh_min:
        booking_record.waitlist_update_time = datetime.now()
        booking_record.save()
        client_session = requests.Session()
        client_session, cookie_jar = cookie_setting(user_id, client_session)
        if cookie_jar is not None:
            response = client_session.get('https://clients.mindbodyonline.com/ASP/my_waitlist.asp',
                                          headers=get_headers())
            # update waitlist items' postions
            soup = BeautifulSoup(response.content, "lxml")
            class_schedule = soup.find("table", {"class": "myInfoTable"})
            # if wait list items exists in mindbody
            # update position, check if any item confirmed from wait list
            if class_schedule:
                table_schedule = get_table(class_schedule)
                if booking_wait_set.exists():
                    # update bookings waitlist position with is_waitlisted status
                    missing_item = []
                    for booking in booking_wait_set:
                        booking_is_missing = True
                        for item in table_schedule:
                            if item[1] == booking.class_item.start_time and \
                                    item[2] == booking.class_item.class_name and \
                                    item[3] == booking.class_item.teacher and \
                                    item[4] == booking.class_item.location:
                                booking_is_missing = False
                                if int(item[6]) != booking.waitlist_position:
                                    booking.waitlist_position = int(item[6])
                                    booking.save()
                                    async_to_sync(channel_layer.group_send)(
                                        group_name,
                                        {
                                            'type': 'send_notification',
                                            'text': {
                                                'message': f"Your latest wait list position for "
                                                           f"{booking.class_item.class_name} with "
                                                           f"{booking.class_item.location} is "
                                                           f"{booking.waitlist_position}, "
                                                           f"refresh to see latest update.",
                                                'level': "info",
                                            }
                                        }
                                    )
                        if booking_is_missing:
                            missing_item.append(booking)
                    # booking_is_missing is true, meaning one or more is_waitlisted item missing
                    # 1. class confirmed from waitlist
                    # 2. user cancel from mindbody
                    if missing_item:
                        check_from_wait_to_schedule(client_session, missing_item, group_name)
                if booking_wait_set.count() != len(table_schedule):
                    for item in table_schedule:
                        class_item = ClassDetail.objects.get(
                            start_time=item[1],
                            class_name=item[2],
                            teacher=item[3],
                            location=item[4],
                            date_time_field=datetime.strptime(item[0] + " " + item[1], '%d/%m/%Y %H:%M')
                        )
                        booking, is_created = Booking.objects.get_or_create(
                            booking_record=booking_record,
                            class_item=class_item,
                            is_waitlisted=True,
                        )
                        if is_created:
                            booking.waitlist_position = int(item[6])
                            booking.token_used = 0
                            booking.save()
                            # messages.info(request, "user added " + booking.class_item.class_name +
                            #               " to Pure wait list, bookasana sync to match wait list.")
                            async_to_sync(channel_layer.group_send)(
                                group_name,
                                {
                                    'type': 'send_notification',
                                    'text': {
                                        'message': "User added " + booking.class_item.class_name +
                                                   " to Pure wait list, bookasana sync to match wait list.",
                                        'level': "info",
                                    }
                                }
                            )
            # if wait list times doesn't exists in mindbody
            # check with schedule table to see if wait list item confirmed
            elif "No Wait Listed" in soup.find("b").get_text():
                if booking_wait_set.exists():
                    check_from_wait_to_schedule(client_session, booking_wait_set, group_name)
            else:
                cookie_jar.delete()
                # messages.info(request, "no response from server, please try again.")
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'send_notification',
                        'text': {
                            'message': "No response from server, please refresh page.",
                            'level': "error",
                        }
                    }
                )
        else:
            # messages.error(request, "invalid login account/password, please check and try again.")
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'send_notification',
                    'text': {
                        'message': "Invalid login account/password, please check and try again.",
                        'level': "error",
                    }
                }
            )
        client_session.close()
    update_user_schedule(user_id)
