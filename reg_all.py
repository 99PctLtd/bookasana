import asyncio
import concurrent.futures
import json
import requests
import sched
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from datetime import datetime, date
from datetime import timedelta

from authentication.models import User
from account.models import Profile, MembershipRecord
from booking.models import BookingRecord, Booking
from timetable.models import ClassDetail, CenterSchedule
from timetable import task_schedule_update as su
import get_user_info as gui


def browser_startup():
    user_agent = f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 " \
                 f"(KHTML, like Gecko) Chrome/60.0.3112.50 Safari/537.36"
    options = webdriver.ChromeOptions()
    # options.add_argument('headless')
    options.add_argument('window-size=1920x1080')
    options.add_argument(f'user-agent={user_agent}')
    return webdriver.Chrome(chrome_options=options)


def check_booking_status(response, package_returned):
    # check booking status
    soup = BeautifulSoup(response.text, "lxml")
    if soup.find("input", {"name": "AddWLButton"}):
        print(f"user on wait list  : {package_returned['booking_info']}")
    elif soup.find("td", {"class": "mainText center-ch"}):
        print(f"wait list is full  : {package_returned['booking_info']}")
        return False
    else:
        # booking successful
        print(f"booking success    : {package_returned['booking_info']}")
        return True


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


# parsing for class_id and update database
def get_class_id(session, cookies_browser, class_detail_queryset, date):
    start_time = time.time()
    for cookies in cookies_browser:
        session.cookies.set(**cookies)
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) '
                      'Gecko/20100101 Firefox/60.0',
    }
    response = session.get(get_schedule_url(date), headers=headers)
    print(f'response took {time.time() - start_time}s.')
    start_time = time.time()
    soup = BeautifulSoup(response.text, 'lxml')
    class_schedule = soup.find(id='classSchedule-mainTable')
    print(f'beautifulsoup took {time.time() - start_time}s.')
    start_time = time.time()
    # parse schedule
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
                        row_temp.append(column.find(
                            "input", {'class': "SignupButton"}
                        ).attrs['name'][3:])
                        column_marker += 1
                else:
                    row_temp.append(column.get_text())
                    column_marker += 1
            table_schedule.append(row_temp)
    del table_schedule[0]
    print(f'prasing schedule took {time.time() - start_time}s.')
    start_time = time.time()
    # clean data
    for row in table_schedule:
        # remove \xa0 from start time
        row[0] = row[0].replace(u'\xa0\xa0\xa0', u'')
        row[0] = row[0].replace(u' ', u'')
        row[0] = row[0].replace(u'\xa0', u' ')
        # replace \xa0 from assistant
        row[4] = row[4].replace(u'\xa0\xa0 ', u'')
        # remove Yoga -
        if row[5] == 'Pure South - The Pulse':
            row[5] = row[5].replace(u'Pure South - ', u'')
        else:
            row[5] = row[5].replace(u'Yoga - ', u'')
        # replace hrs with mins
        if row[6] == '\xa04\xa0hours':
            row[6] = row[6].replace(u'\xa04\xa0hours', u'240 mins')
        elif row[6] == '\xa02\xa0hours\xa0and\xa030\xa0minutes':
            row[6] = row[6].replace(u'\xa02\xa0hours\xa0and\xa030\xa0minutes',
                                    u'150 mins')
        elif row[6] == '\xa02\xa0hours\xa0and\xa020\xa0minutes':
            row[6] = row[6].replace(u'\xa02\xa0hours\xa0and\xa020\xa0minutes',
                                    u'140 mins')
        elif row[6] == '\xa02\xa0hours':
            row[6] = row[6].replace(u'\xa02\xa0hours', u'120 mins')
        elif row[6] == '\xa01\xa0hour\xa0and\xa030\xa0minutes':
            row[6] = row[6].replace(u'\xa01\xa0hour\xa0and\xa030\xa0minutes',
                                    u'90 mins')
        elif row[6] == '\xa01\xa0hour\xa0and\xa015\xa0minutes':
            row[6] = row[6].replace(u'\xa01\xa0hour\xa0and\xa015\xa0minutes',
                                    u'75 mins')
        elif row[6] == '\xa01\xa0hour':
            row[6] = row[6].replace(u'\xa01\xa0hour', u'60 mins')
        elif row[6] == '\xa030\xa0minutes':
            row[6] = row[6].replace(u'\xa030\xa0minutes', u'30 mins')
        elif row[6] == '\xa020\xa0minutes':
            row[6] = row[6].replace(u'\xa020\xa0minutes', u'20 mins')
        elif row[6] == '\xa015\xa0minutes':
            row[6] = row[6].replace(u'\xa015\xa0minutes', u'15 mins')
        elif row[6] == '\xa010\xa0minutes':
            row[6] = row[6].replace(u'\xa010\xa0minutes', u'10 mins')
    print(f'clean data took {time.time() - start_time}s.')
    start_time = time.time()
    # save class_id
    for row in table_schedule:
        detail, is_created = class_detail_queryset.get_or_create(
            start_time=row[0],
            class_name=row[2],
            teacher=row[3],
            location=row[5],
        )
        detail.class_id = row[1]
        detail.save()
    print(f'parsing class id took {time.time() - start_time}s.')


# extract listed class primary key into dictionary, with user_pk as key
def get_class_list(user_pk, date):
    class_pk = {}
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
                class_id_user.append(booking.class_item.pk)
        class_pk[str(u_pk)] = class_id_user
    return class_pk


def get_schedule_cookie():
    print(f'parsing general cookie with selenium...')
    start_time = time.time()
    url_login = f"https://clients.mindbodyonline.com/classic/mainclass?studioid=81" \
                f"&tg=&vt=&lvl=&stype=&view=&trn=0&page=&catid=&prodid=&date=" \
                f"{datetime.today().strftime('%m')}%2f{datetime.today().strftime('%d')}" \
                f"%2f{datetime.today().strftime('%Y')}&classid=0&prodGroupId=&sSU=" \
                f"&optForwardingLink=&qParam=&justloggedin=&nLgIn=&pMode=0"
    driver = browser_startup()
    driver.get(url_login)
    WebDriverWait(driver, 10).until(
        ec.visibility_of_element_located((By.ID, "requiredtxtUserName"))
    )
    cookies = driver.get_cookies()
    driver.quit()
    print(f'parsing general cookies took {time.time() - start_time}s.')
    print()
    return cookies


def get_user_cookie_token_ref(user_pk, user_info):
    user = User.objects.get(pk=user_pk)
    profile = Profile.objects.get(user=user)
    print(f'parsing {user.username}...')
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) '
                      'Gecko/20100101 Firefox/60.0',
    }
    data_login = {
        'requiredtxtUserName': user_info['username'],
        'requiredtxtPassword': user_info['password'],
    }
    s = requests.Session()
    for x in range(3):
        s.get(get_schedule_url(), headers=headers)
    response = s.post('https://clients.mindbodyonline.com/Login?'
                      'studioID=81&isLibAsync=true&isJson=true',
                      headers=headers, data=data_login)
    # get CSRFToken & cookies & update ref number
    if json.loads(response.text)['json']['success']:
        # this mindbody page has extremely slow response
        # will have to look into this for updating client membership info
        response = s.get('https://clients.mindbodyonline.com/ASP/my_ph.asp',
                         headers=headers)
        soup = BeautifulSoup(response.text, "lxml")
        # get CSRFToken & cookies
        print(f'{user.username} - parsing cookies and token...')
        csrf_token = soup.find("input", {"name": "CSRFToken"}).get('value')
        cookies_login = s.cookies.get_dict()
        s.close()
        # check and update ref number
        print(f'{user.username} - checking booking ref. number...')
        if profile.membership_exp_yoga <= date.today():
            print(f'{user.username} - updating yoga membership...')
            # updating membership record
            membership_record = MembershipRecord.objects.get(
                profile=profile,
                payment_ref=profile.membership_ref_yoga,
            )
            membership_record.available = False
            membership_record.save()
            # get the new membership record and update current yoga membership ref
            client_account = soup.find("table", {"class": "myInfoTable"})
            account_table = gui.parse_html_table(client_account)
            gui.save_to_database(profile, account_table)
            gui.set_current_membership(profile)
            # update user_info
            profile.update()
            user_info['membership_ref_yoga'] = profile.membership_ref_yoga
        else:
            print(f'{user.username} - yoga membership valid')
        return user_pk, cookies_login, csrf_token
    else:
        print(f'{user.username} - login email and password invalid for logging in.')
        return None


# takes date, return user's primary key on that date
def get_listed_user(date):
    user_pk = []
    for booking in Booking.objects.filter(is_listed=True):
    # for booking in Booking.objects.filter(is_booked_currently=True):
        if booking.class_item.center_schedule.date == date:
            if booking.booking_record.owner.user.pk not in user_pk:
                user_pk.append(booking.booking_record.owner.user.pk)
    return user_pk


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


# take user primary key, returns user info
def get_user_info(user_pk):
    if user_pk:
        user_info = {}
        for user in user_pk:
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
def packaging_class(user_pk_set, user_info_set, user_cookie_jar, user_token, user_class_list_pk):
    package = []
    for user_pk in user_pk_set:
        for class_pk in user_class_list_pk[str(user_pk)]:
            user = User.objects.get(pk=user_pk)
            class_detail = ClassDetail.objects.get(pk=class_pk)
            booking_link = get_studio_links(class_detail.location)
            package.append({
                'headers': {
                    'User-Agent': f"Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) "
                                  f"Gecko/20100101 Firefox/60.0"
                },
                'payload_book': {
                    'CSRFToken': user_token[str(user_pk)],
                    'lastClientID': user_info_set[str(user_pk)]['client_id'],
                },
                'cookies_jar': user_cookie_jar[str(user_pk)],
                'url_link': f"{booking_link[0]}{class_detail.class_id}"
                            f"{booking_link[1]}{class_detail.date_time_field.date().strftime('%-m/%-d/%Y')}"
                            f"{booking_link[2]}{user_info_set[str(user_pk)]['membership_ref_yoga']}"
                            f"{booking_link[3]}",
                'booking_info': f'{class_detail} for {user.username}',
                'class_id': str(class_detail.class_id),
                'class_date': class_detail.date_time_field.date().strftime('%-m/%-d/%Y'),
            })
    return package


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
    # print(f'{package["booking_info"]}')
    return response, package


def schedule_update(cookies, date):
    print(f'updating {date} schedule...')
    print('==================================================')
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
async def main(date=(datetime.today() + timedelta(days=2)).strftime('%Y%m%d')):
    # get user info with listed booking
    try:
        user_pk_set = get_listed_user(date)
        user_info_set = get_user_info(user_pk_set)
    except TypeError:
        print('there is no listed class from any user.')
        user_pk_set, user_info_set = None, None
    if user_pk_set and user_info_set:
        print(f'start parsing cookies and token...')
        start_time = time.time()
        # to-do:
        # ==================================================
        # check and update user payment ref#
        user_cookie_token = [
            get_user_cookie_token_ref(
                user_pk, user_info_set[str(user_pk)]
            ) for user_pk in user_pk_set
        ]
        print(f'parsing user cookies, token and check booking '
              f'ref. number took {time.time() - start_time}s.')
        schedule_cookie = clean_cookie(get_schedule_cookie())
        user_cookie_jar, user_token = extract_cookie_token(user_cookie_token)
        user_class_list_pk = get_class_list(user_pk_set, date)
        # update schedule at 8:59am
        # scrap for class_id at 9am
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
        sec_until_0900 = (datetime.strptime(
            datetime.today().strftime('%Y-%m-%d') + ' 09:00:00', '%Y-%m-%d %H:%M:%S'
        ) - datetime.now()).total_seconds()
        center_schedule = CenterSchedule.objects.get(date=date)
        class_details = ClassDetail.objects.filter(center_schedule=center_schedule)
        sch_task.enter(sec_until_0900,
                       1,
                       get_class_id,
                       argument=(
                           session_booking,
                           schedule_cookie,
                           class_details,
                           date
                       ))
        sch_task.run()
        # book all listed classes
        package_class = packaging_class(
            user_pk_set, user_info_set, user_cookie_jar,
            user_token, user_class_list_pk,
        )

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            loop = asyncio.get_event_loop()
            futures = [
                loop.run_in_executor(
                    executor,
                    package_requests,
                    a
                    package
                ) for package in package_class
            ]
            print(f'done sending requests for class booking '
                  f'in {time.time() - start_time}s...')
            print(f'done booking in {time.time() - start_time}s...')
            print(f'==================================================')
            print(f'checking booking status...')
            for response, package_returned in await asyncio.gather(*futures):
                check_booking_status(response, package_returned)
    else:
        print('there is no listed class from any user.')


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
