from django.core.management.base import BaseCommand, CommandError
import asyncio
import concurrent.futures
import json
import lxml.html
import requests
import sched
import time

from bs4 import BeautifulSoup
from celery import shared_task
from decouple import config
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from datetime import datetime, date
from datetime import timedelta

from authentication.models import User
from account.models import Profile, MembershipRecord
from booking import book_class as bc
from booking.models import BookingRecord, Booking
from timetable.models import ClassDetail, CenterSchedule
from timetable import task_schedule_update as su
import authentication.task_confirmation_check as tcc


class Command(BaseCommand):
    help = "to register all user's listed bookings."

    def handle(self, *args, **options):
        try:
            loop = asyncio.get_event_loop()
            for days in range(2, -1, -1):
                loop.run_until_complete(main(days))
        except CommandError as e:
            raise print(e)


def browser_startup():
    user_agent = f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 " \
                 f"(KHTML, like Gecko) Chrome/60.0.3112.50 Safari/537.36"
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('window-size=1920x1080')
    options.add_argument(f'user-agent={user_agent}')
    # better to set path to chromedriver direcly in script
    return webdriver.Chrome(
        config('CHROMEDRIVER', default='/usr/local/bin/chromedriver'),
        chrome_options=options
    )


def check_booking_status(response, package_returned):
    # check booking status
    booking = Booking.objects.get(pk=package_returned['booking_pk'])
    soup = BeautifulSoup(response.text, "lxml")
    if soup.find("input", {"name": "AddWLButton"}):
        bc.set_booking_status_single(booking, is_waitlisted=True)
        get_booking_wait_position.delay(
            booking.id,
            package_returned['cookies_jar'],
            package_returned['payload_book']['CSRFToken'],
            package_returned['class_id'],
            package_returned['class_date']
        )
        print(f"user on wait list  : {package_returned['token_used']} - {package_returned['booking_info']}")
    elif soup.find("td", {"class": "mainText center-ch"}):
        # need to set up a way to notify user booking failed
        # possible a notification app to keep track of all notifications
        booking.delete()
        print(f"wait list is full  : {package_returned['token_used']} - {package_returned['booking_info']}")
    elif "scheduling is currently closed" in soup.find("script").get_text().lower():
        print(f"scheduling closed  : {package_returned['token_used']} - {package_returned['booking_info']}")
    else:
        # booking successful, deduct token from user
        user = User.objects.get(id=package_returned['user_id'])
        profile = Profile.objects.get(user=user)
        profile.token_single -= booking.token_used
        profile.save()
        bc.set_booking_status_single(booking, is_booked_currently=True)
        get_booking_visit_id.delay(booking.id, package_returned['cookies_jar'])
        print(f"booking success    : {package_returned['token_used']} - {package_returned['booking_info']}")


def clean_cookie(cookies):
    for cookie in cookies:
        if "expiry" in cookie:
            del cookie["expiry"]
        if "httpOnly" in cookie:
            del cookie["httpOnly"]
    return cookies


# cookie_jar and token dictionary with user_pk as key
def extract_cookie_token(user_cookie_token):
    cookies_jar = {}
    token = {}
    for data in user_cookie_token:
        cookies_jar[str(data[0])] = data[1]
        token[str(data[0])] = data[2]
    return cookies_jar, token


@shared_task()
def get_booking_visit_id(booking_id, cookie_jar):
    booking = Booking.objects.get(id=booking_id)
    client_session = requests.Session()
    for cookies in cookie_jar:
        client_session.cookies.set(cookies, cookie_jar[cookies])
    response = client_session.post('https://clients.mindbodyonline.com/ASP/my_sch.asp',
                                   headers=get_headers())
    soup = BeautifulSoup(response.content, "lxml")
    class_schedule = soup.find("table", {"class": "myInfoTable"})
    table_schedule = bc.get_table(class_schedule)
    bc.update_single_schedule(table_schedule, booking)
    client_session.close()


@shared_task()
def get_booking_wait_position(booking_id, cookie_jar, csrf_token, class_id, class_date):
    booking = Booking.objects.get(id=booking_id)
    client_session = requests.Session()
    for cookies in cookie_jar:
        client_session.cookies.set(cookies, cookie_jar[cookies])
    data_waitlist = {
        'CSRFToken': csrf_token,
        'frmClassID': class_id,
        'frmClassDate': class_date,
    }
    response = client_session.post('https://clients.mindbodyonline.com/ASP/waitlist_a.asp',
                                   headers=get_headers(), data=data_waitlist)
    soup = BeautifulSoup(response.content, "lxml")
    class_schedule = soup.find("table", {"class": "myInfoTable"})
    table_schedule = bc.get_table(class_schedule)
    bc.update_single_waitlist(table_schedule, booking)


# parsing for class_id and update database
def get_class_id(session, class_detail_queryset, date):
    start_time, stage_time = time.time(), time.time()
    response = session.get(get_schedule_url(date), headers=get_headers())

    print()
    print(f"stage    : {time.time() - stage_time}s to response.")
    stage_time = time.time()

    doc = lxml.html.fromstring(response.content)
    class_rows = doc.xpath("//table[@id='classSchedule-mainTable']/tr[@class='evenRow' "
                           "or @class='oddRow']")
    all_classes = []
    for row in class_rows:
        row_clean = [x.text for x in row.xpath(".//*") if x.text is not None]
        row_id = row.xpath(".//td/input/@name")
        if row_id:
            row_clean.insert(1, row_id[0][3:])
        else:
            row_clean.insert(1, "")
        all_classes.append(row_clean)

    # clean data
    for row in all_classes:
        # remove \xa0 from start time
        row[0] = row[0].replace(u'\xa0\xa0\xa0', u'')
        row[0] = row[0].replace(u' ', u'')
        row[0] = row[0].replace(u'\xa0', u' ')
        row[0] = datetime.strptime(row[0], '%I:%M %p').strftime('%H:%M')

    print(f"stage    : {time.time() - stage_time}s to parse schedule table.")
    stage_time = time.time()

    # save class_id
    for row in all_classes:
        class_detail_queryset.filter(
            start_time=row[0],
            teacher=row[3],
        ).update(class_id=row[1])
    print(f"stage    : {time.time() - stage_time}s to update database.")
    print(f'overall  : {time.time() - start_time}s to get_class_id() with lxml parser.')
    print(f'==================================================')


# extract listed class primary key into dictionary, with user_pk as key
def get_booking_list(user_pk, date):
    booking_pk = {}
    for u_pk in user_pk:
        user = User.objects.get(pk=u_pk)
        profile = Profile.objects.get(user=user)
        booking_record = BookingRecord.objects.get(owner=profile)
        bookings = Booking.objects.filter(is_listed=True,
                                          booking_record=booking_record)
        # bookings = Booking.objects.filter(is_booked_currently=True,
        #                                   booking_record=booking_record)
        class_id_user = []
        for booking in bookings:
            if booking.class_item.center_schedule.date == date:
                class_id_user.append(booking.pk)
        booking_pk[str(u_pk)] = class_id_user
    return booking_pk


# TO-DO: set up with various headers and rotate automatically
def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0',
    }


def get_holiday_list(this_year):
    session_holiday = requests.session()
    response = session_holiday.get(
        f"https://www.gov.hk/en/about/abouthk/holiday/{this_year}.htm"
    )
    soup = BeautifulSoup(response.text, "lxml")
    holiday_table = soup.find("tbody")
    holiday_list = []
    try:
        for row in holiday_table.find_all('tr')[1:]:
            holiday = row.find("td", {"class": "date"}).get_text()
            holiday_list.append(
                (datetime.strptime(f"{holiday} 2019", '%d %B %Y').strftime('%Y%m%d'))
            )
    except TypeError as message:
        print(f"TypeError: {message}")
        print(f"technical issue with www.gov.hk website...")
    except ValueError as message:
        print(f"ValueError: {message}")
        print(f"technical issue with www.gov.hk website...")
    finally:
        session_holiday.close()
        return holiday_list


# takes date, return user's primary key on that date
def get_listed_user(date):
    user_pk = []
    for booking in Booking.objects.filter(is_listed=True):
    # for booking in Booking.objects.filter(is_booked_currently=True):
        if booking.class_item.center_schedule.date == date:
            if booking.booking_record.owner.user.pk not in user_pk:
                user_pk.append(booking.booking_record.owner.user.pk)
    return user_pk


# takes "weekdays", "weekends" and "holiday"
# return priority list for order_by
def get_priority_list(*args):
    # this part has to evolve over time
    # possibly start taking class popularity data to impove this list
    if args == "weekends" or args == "holiday":
        return [
            ['class_name', 'Aerial Yoga 1'],
            ['class_name', 'Aerial Yoga 2'],
            ['class_name', 'Wall Rope Yoga 1'],
            ['teacher', 'Tin Ming Lau'],
            ['location', 'Langham Place Office Tower'],
            ['location', 'Starstreet Precinct'],
            ['location', 'World Trade Centre'],
            ['location', 'Pacific Place'],
        ]
    else:
        return [
            ['class_name', 'Aerial Yoga 1'],
            ['class_name', 'Aerial Yoga 2'],
            ['class_name', 'Wall Rope Yoga 1'],
            ['teacher', 'Tin Ming Lau'],
            ['start_time', '19:00'],
            ['start_time', '19:15'],
            ['start_time', '19:30'],
            ['start_time', '19:45'],
            ['start_time', '18:45'],
            ['start_time', '20:00'],
            ['start_time', '18:30'],
            ['start_time', '18:30'],
            ['location', 'Langham Place Office Tower'],
            ['location', 'Starstreet Precinct'],
            ['location', 'World Trade Centre'],
            ['location', 'Pacific Place'],
        ]


def get_schedule_cookie():
    print(f'parsing general cookie with selenium...')
    start_time = time.time()
    url_login = f"https://clients.mindbodyonline.com/classic/mainclass?studioid=81" \
                f"&tg=&vt=&lvl=&stype=&view=&trn=0&page=&catid=&prodid=&date=" \
                f"{datetime.today().strftime('%m')}%2f{datetime.today().strftime('%d')}" \
                f"%2f{datetime.today().strftime('%Y')}&classid=0&prodGroupId=&sSU=" \
                f"&optForwardingLink=&qParam=&justloggedin=&nLgIn=&pMode=0"

    # display = Display(visible=0, size=(1920, 1080))
    # display.start()

    driver = browser_startup()
    driver.get(url_login)
    WebDriverWait(driver, 10).until(
        ec.visibility_of_element_located((By.ID, "requiredtxtUserName"))
    )
    cookies = driver.get_cookies()
    driver.quit()

    # display.stop()

    print(f'parsing general cookies took {time.time() - start_time}s.')
    print('==================================================')
    return cookies


# takes date, return schedule url of that day
def get_schedule_url(schedule_date=datetime.today().strftime('%Y%-m%-d')):
    try:
        return f"https://clients.mindbodyonline.com/classic/mainclass?studioid=81" \
               f"&tg=&vt=&lvl=&stype=&view=&trn=0&page=&catid=&prodid=" \
               f"&date={schedule_date[4:6]}%2f{schedule_date[6:]}%2f" \
               f"{schedule_date[:4]}&classid=0&prodGroupId=&sSU=&" \
               f"optForwardingLink=&qParam=&justloggedin=&nLgIn=&pMode=0"
    except TypeError:
        print('TypeError: date has to be an integer.')


# should return only the link for one studio
def get_studio_links(location):
    # class_id_num, booking_date, membership_ref_yoga to be fill inbetween
    if location == 'Asia Standard Tower':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=16&typeGroupID=22&recurring=false&wlID="]
    elif location == 'Grand Century Place':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=28&typeGroupID=24&recurring=false&wlID="]
    elif location == 'Hutchison House':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=24&typeGroupID=67&recurring=false&wlID="]
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
    elif location == 'Millennium City 5':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=29&typeGroupID=74&recurring=false&wlID="]
    elif location == 'Pacific Place':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=26&typeGroupID=72&recurring=false&wlID="]
    elif location == 'Peninsula Office Tower':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=7&typeGroupID=41&recurring=false&wlID="]
    elif location == 'Soundwill Plaza':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=3&typeGroupID=23&recurring=false&wlID="]
    elif location == 'Starstreet Precinct':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=30&typeGroupID=72&recurring=false&wlID="]
    elif location == 'The Centrium':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=1&typeGroupID=2&recurring=false&wlID="]
    elif location == 'The Pulse':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=22&typeGroupID=65&recurring=false&wlID="]
    elif location == 'World Trade Centre':
        return ["https://clients.mindbodyonline.com/ASP/res_deb.asp?classID=",
                "&courseid=&classDate=",
                "&pmtRefNo=",
                "&clsLoc=27&typeGroupID=23&recurring=false&wlID="]
    else:
        print('new center to be add...')
    return None


# prase user cookie, csrf and membership ref
# also check if membership ref is valid
def get_user_cookie_token_ref(user_pk, user_info):
    user = User.objects.get(pk=user_pk)
    profile = Profile.objects.get(user=user)
    print(f'parsing {user.username}...')
    data_login = {
        'requiredtxtUserName': user_info['username'],
        'requiredtxtPassword': user_info['password'],
    }
    s = requests.Session()
    for x in range(3):
        s.get(get_schedule_url(), headers=get_headers())
    response = s.post('https://clients.mindbodyonline.com/Login?'
                      'studioID=81&isLibAsync=true&isJson=true',
                      headers=get_headers(), data=data_login)
    # get CSRFToken & cookies & update ref number
    if json.loads(response.text)['json']['success']:
        # this mindbody page has extremely slow response
        # will have to look into this for updating client membership info
        response = s.get('https://clients.mindbodyonline.com/ASP/my_ph.asp',
                         headers=get_headers())
        soup = BeautifulSoup(response.text, "lxml")
        # get CSRFToken & cookies
        print()
        print(f'{user.username} - parsing cookies and token...')
        csrf_token = soup.find("input", {"name": "CSRFToken"}).get('value')
        cookies_login = s.cookies.get_dict()
        s.close()
        # check and update ref number
        print(f'{user.username} - checking booking ref. number...')
        if profile.membership_exp_yoga <= date.today():
            print(f'{user.username} - updating yoga membership...')

            # get the new membership record and update current yoga membership ref
            client_account = soup.find("table", {"class": "myInfoTable"})
            account_table = tcc.parse_html_table(client_account)
            tcc.save_account_to_database(profile, account_table)
            tcc.set_current_membership(profile)

            # update user_info
            if profile.membership_exp_yoga <= date.today():
                # message log here
                # delete operation outside when other lists are available
                print(f"{user.username} - removed from reservation list...")
                return None
            else:
                user_info['membership_ref_yoga'] = profile.membership_ref_yoga
        else:
            print(f"{user.username} - yoga membership valid")
        return user_pk, cookies_login, csrf_token
    else:
        print()
        print(f"{user.username} - login email and password invalid for logging in.")
        return None


# take user primary key, returns user info
def get_user_info(user_pk):
    if user_pk:
        user_info = {}
        for user in user_pk:
            # to-do:
            # ==================================================
            # check and update user payment ref# / Membership ref yoga# / Membership ref fitness#
            uo = User.objects.get(pk=user)
            profile = Profile.objects.get(user=uo)
            user_info[str(user)] = {
                'username': uo.pure_login,
                'password': uo.pure_password,
                'client_id': profile.client_id,
                'membership_ref_yoga': profile.membership_ref_yoga,
            }
        return user_info
    return None


# package all necessary info into requests link and session.cookies
# ==================================================
# to-do : arrange requests by priority
def packaging_class(user_pk_set, user_info_set, user_cookie_jar, user_token, user_booking_list_pk):
    packages = []
    for user_pk in user_pk_set:
        for booking_pk in user_booking_list_pk[str(user_pk)]:
            user = User.objects.get(pk=user_pk)
            booking = Booking.objects.get(pk=booking_pk)
            class_detail = ClassDetail.objects.get(pk=booking.class_item.pk)
            packages.append({
                'booking_pk': booking_pk,
                'booking_info': f'{class_detail} for {user.username}',
                'class_date': class_detail.date_time_field.date().strftime('%-m/%-d/%Y'),
                'cookies_jar': user_cookie_jar[str(user_pk)],
                'headers': get_headers(),
                'payload_book': {
                    'CSRFToken': user_token[str(user_pk)],
                    'lastClientID': user_info_set[str(user_pk)]['client_id'],
                },
                'user_id': str(user_pk),
                # for sorting use | package_to_sort()
                'class_name': class_detail.class_name,
                'start_time': class_detail.start_time,
                'teacher': class_detail.teacher,
                'location': class_detail.location,
                'token_used': booking.token_used,
            })
    return packages


def packaging_class_id(package_class, user_info_set):
    for package in package_class:
        booking = Booking.objects.get(pk=package['booking_pk'])
        user_pk = booking.booking_record.owner.pk
        class_detail = ClassDetail.objects.get(pk=booking.class_item.pk)
        booking_link = get_studio_links(class_detail.location)
        package['class_id'] = str(class_detail.class_id)
        package['url_link'] = f"{booking_link[0]}{class_detail.class_id}" \
                              f"{booking_link[1]}{class_detail.date_time_field.date().strftime('%-m/%-d/%Y')}" \
                              f"{booking_link[2]}{user_info_set[str(user_pk)]['membership_ref_yoga']}" \
                              f"{booking_link[3]}"
    return package_class


# book class
# session, package[{cookies and requests link}]
def package_requests(session, package):
    # pass cookies to request session
    session.cookies.clear()
    for cookies in package['cookies_jar']:
        session.cookies.set(cookies, package['cookies_jar'][cookies])
    response = session.post(
        package['url_link'],
        headers=package['headers'],
        data=package['payload_book']
    )
    print(f"sent               : {package['token_used']} - {package['booking_info']}")
    return response, package


def package_to_sort(date, package_class, holiday):
    day = datetime.strptime(date, '%Y%m%d').strftime('%A')
    if date in holiday or day == "Saturday" or day == "Sunday":
        priority_list = get_priority_list("weekends")
    else:
        priority_list = get_priority_list("weekdays")
    # sort against priority list item by item
    # within each item, arrange by token_used
    package_sorted = []
    for priority_item in priority_list:
        item_sorted = []
        for x in range(len(package_class) - 1, -1, -1):
            package = package_class[x]
            if package[priority_item[0]] == priority_item[1]:
                item_sorted.append(package)
                del package_class[x]
        package_sorted.append(sorted(item_sorted,
                                     key=lambda item_list: item_list['token_used'],
                                     reverse=True))
    # arrange non-priority items by token_used
    package_sorted.append(sorted(package_class,
                                 key=lambda item_list: item_list['token_used'],
                                 reverse=True))
    # extract items back into a list
    package_extracted = []
    for items in package_sorted:
        for item in items:
            package_extracted.append(item)
    return package_extracted


def schedule_update(cookies, date):
    print()
    print(f'updating {date} schedule...')
    try:
        su.get_latest_timetable(cookies, date)
        su.update_timetable(date)
    finally:
        su.clean_temp_table()


# booking for default date set 2 days from now.
# this script should only book for 2 days from today,
# as it is the most competitive to book
# ======================================================================
# TO-DO LIST
# check if login name and password valid, if not take out account from list
async def main(days):
    date = (datetime.today() + timedelta(days=days)).strftime('%Y%m%d')

    # get user info with listed booking
    try:
        user_pk_set = get_listed_user(date)
        # to-do:
        # ==================================================
        # check and update user payment ref#
        user_info_set = get_user_info(user_pk_set)
    except TypeError:
        print(f'==================================================')
        print(f'{date}           : there is no listed class from any user.')
        user_pk_set, user_info_set = None, None

    if user_pk_set and user_info_set:
        print(f'==================================================')
        print(f'{date}           : start parsing cookies and token...')
        print()
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            loop = asyncio.get_event_loop()
            futures = [
                loop.run_in_executor(
                    executor,
                    get_user_cookie_token_ref,
                    user_pk,
                    user_info_set[str(user_pk)]
                ) for user_pk in user_pk_set
            ]
            user_cookie_token = await asyncio.gather(*futures)

        # if user_cookie_token['user'] == None
        # meaning user login or membership ref invalid, remove from all data sets
        for x in range(len(user_cookie_token) - 1, -1, -1):
            if not user_cookie_token[x]:
                del user_cookie_token[x]
                del user_info_set[str(user_pk_set[x])]
                del user_pk_set[x]

        print()
        print(f'parsing user cookies, token and check booking '
              f'ref. number took {time.time() - start_time}s.')
        print(f'==================================================')
        schedule_cookie = clean_cookie(get_schedule_cookie())
        user_cookie_jar, user_token = extract_cookie_token(user_cookie_token)
        user_booking_list_pk = get_booking_list(user_pk_set, date)
        package_class_initial = packaging_class(
            user_pk_set, user_info_set, user_cookie_jar,
            user_token, user_booking_list_pk,
        )
        package_class_sorted = package_to_sort(date, package_class_initial, get_holiday_list(date[:4]))
        print(f'sorted list of bookings:')
        for pcs in package_class_sorted:
            print(f"sorted             : {pcs['token_used']} - {pcs['booking_info']}")
        print(f'==================================================')
        # update schedule at 8:59am, scrap for class_id at 9am
        print(f'pending to update schedule on '
              f'{datetime.today().strftime("%Y-%m-%d")} '
              f'at 8:59 and get class_id @ 9... ')
        session_booking = requests.Session()
        for cookies in schedule_cookie:
            session_booking.cookies.set(**cookies)
        sch_task = sched.scheduler(time.time, time.sleep)
        sec_until_0859 = (datetime.strptime(
            datetime.today().strftime('%Y-%m-%d') + ' 08:59:00', '%Y-%m-%d %H:%M:%S'
        ) - datetime.now()).total_seconds()
        sch_task.enter(sec_until_0859,
                       1,
                       schedule_update,
                       argument=(
                           session_booking,
                           date
                       ))
        center_schedule = CenterSchedule.objects.get(date=date)
        class_details = ClassDetail.objects.filter(center_schedule=center_schedule)
        sec_until_0900 = (datetime.strptime(
            datetime.today().strftime('%Y-%m-%d') + ' 09:00:00', '%Y-%m-%d %H:%M:%S'
        ) - datetime.now()).total_seconds()
        sch_task.enter(sec_until_0900,
                       1,
                       get_class_id,
                       argument=(
                           session_booking,
                           class_details,
                           date
                       ))
        sch_task.run()

        # book all listed classes
        start_time = time.time()
        package_sorted_w_id = packaging_class_id(package_class_sorted, user_info_set)
        print(f'done packaging class id '
              f'in {time.time() - start_time}s...')
        print()
        for pcs in package_sorted_w_id:
            print(f"sorted w id        : {pcs['token_used']} - {pcs['class_id']} - {pcs['booking_info']}")
        print(f'==================================================')
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            loop = asyncio.get_event_loop()
            futures = [
                loop.run_in_executor(
                    executor,
                    package_requests,
                    session_booking,
                    package,
                ) for package in package_sorted_w_id
            ]
            print(f'done sending requests for class booking '
                  f'in {time.time() - start_time}s...')
            print(f'==================================================')
            print(f'checking booking status...')
            for response, package_returned in await asyncio.gather(*futures):
                check_booking_status(response, package_returned)
            print(f'==================================================')
        session_booking.close()
    else:
        print(f"{date} : there is no listed class from any user.")
        print(f'==================================================')
