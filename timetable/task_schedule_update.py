# schedule_update should be ran every hour automatically to check on update
from __future__ import absolute_import

import requests
from bs4 import BeautifulSoup
from celery import shared_task
from decouple import config
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
from datetime import timedelta
from timetable.models import Center, CenterSchedule, ClassDetail


def browser_startup():
    user_agent = f'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ' \
                 f'(KHTML, like Gecko) Chrome/60.0.3112.50 Safari/537.36'
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('window-size=1920x1080')
    options.add_argument(f'user-agent={user_agent}')
    return webdriver.Chrome(
        config('CHROMEDRIVER', default='/usr/local/bin/chromedriver'),
        chrome_options=options
    )


def clean_temp_table():
    if CenterSchedule.objects.filter(date='00000000').exists():
        CenterSchedule.objects.filter(date='00000000').delete()


def get_browser_cookies():
    # display = Display(visible=0, size=(1920, 1080))
    # display.start()
    driver = browser_startup()
    driver.get(get_schedule_url())
    request_cookies_browser = None
    try:
        WebDriverWait(driver, 30).until(
            EC.visibility_of_element_located(
                (By.ID, "requiredtxtUserName")
            )
        )
        # passing cookies from webdrive to requests.Session()
        request_cookies_browser = driver.get_cookies()
        for cookies in request_cookies_browser:
            if "expiry" in cookies:
                del cookies["expiry"]
            if "httpOnly" in cookies:
                del cookies["httpOnly"]
    except TimeoutException as ex:
        print("Exception has been thrown. " + str(ex))
    finally:
        driver.quit()
        # display.stop()
        return request_cookies_browser


# return class size for class type
def get_class_capacity(class_name):
    if "aerial" in class_name.lower():
        return 10
    if "Wall Rope" in class_name.lower():
        return 12
    return 30


# get timetable from web and save under center_schedule='00000000'
def get_latest_timetable(session, date):
    headers = {
        'User-Agent': f'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; '
                      f'rv:60.0) Gecko/20100101 Firefox/60.0',
    }
    response = session.get(get_schedule_url(date), headers=headers)
    soup = BeautifulSoup(response.text, 'lxml')
    class_schedule = soup.find(id='classSchedule-mainTable')
    # parse schedule
    table_schedule = []
    try:
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
    except AttributeError as message:
        print(message)
        print(class_schedule)
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
        elif row[6] == '\xa055\xa0minutes':
            row[6] = row[6].replace(u'\xa055\xa0minutes', u'55 mins')
        elif row[6] == '\xa050\xa0minutes':
            row[6] = row[6].replace(u'\xa050\xa0minutes', u'50 mins')
        elif row[6] == '\xa045\xa0minutes':
            row[6] = row[6].replace(u'\xa045\xa0minutes', u'45 mins')
        elif row[6] == '\xa035\xa0minutes':
            row[6] = row[6].replace(u'\xa035\xa0minutes', u'35 mins')
        elif row[6] == '\xa030\xa0minutes':
            row[6] = row[6].replace(u'\xa030\xa0minutes', u'30 mins')
        elif row[6] == '\xa020\xa0minutes':
            row[6] = row[6].replace(u'\xa020\xa0minutes', u'20 mins')
        elif row[6] == '\xa015\xa0minutes':
            row[6] = row[6].replace(u'\xa015\xa0minutes', u'15 mins')
        elif row[6] == '\xa010\xa0minutes':
            row[6] = row[6].replace(u'\xa010\xa0minutes', u'10 mins')
    # save to database temporary for comparision
    center = Center.objects.get(type='yoga', city='hong kong')
    center_schedule_temp = center.centerschedule_set.create(date='00000000')
    for row in table_schedule:
        date_time_str = date + str(row[0])
        date_time_field = datetime.strptime(date_time_str, '%Y%m%d%I:%M %p')
        start_time = date_time_field.strftime('%H:%M')
        center_schedule_temp.classdetail_set.create(
            start_time=start_time,
            class_id=row[1],
            class_name=row[2],
            teacher=row[3],
            assistant=row[4],
            location=row[5],
            duration=row[6],
            date_time_field=date_time_field,
            capacity=get_class_capacity(row[2]),
        )


def get_schedule_url(date=datetime.today().strftime('%Y%m%d')):
    try:
        return f"https://clients.mindbodyonline.com/classic/mainclass?studioid=81" \
               f"&tg=&vt=&lvl=&stype=&view=&trn=0&page=&catid=&prodid=&date=" \
               f"{date[4:6]}%2f{date[6:]}%2f{date[:4]}&classid=0&prodGroupId=&" \
               f"sSU=&optForwardingLink=&qParam=&justloggedin=&nLgIn=&pMode=0"
    except TypeError:
        print('TypeError: date has to be an integer.')


# made change to /60 and 30 mins instead of 15 mins
def is_within_30_min(detail_latest, current_queryset):
    detail_current_set = current_queryset.filter(
        location=detail_latest.location,
        class_name=detail_latest.class_name,
        teacher=detail_latest.teacher
    )
    for detail_current in detail_current_set:
        if abs((detail_current.date_time_field -
                detail_latest.date_time_field).total_seconds()/60) <= 30:
            if detail_current_set.count() == 1:
                return detail_current.pk
    return None


def update_class_id(date):
    center_schedule_new = CenterSchedule.objects.filter(date='00000000')
    center_schedule_cur = CenterSchedule.objects.filter(date=date)
    if center_schedule_new.exists() and center_schedule_cur.exists():
        class_detail_new = ClassDetail.objects.filter(
            center_schedule=center_schedule_new[0]).order_by('date_time_field', 'teacher')
        class_detail_cur = ClassDetail.objects.filter(
            center_schedule=center_schedule_cur[0]).order_by('date_time_field', 'teacher')
        for cd_new, cd_cur in zip(class_detail_new, class_detail_cur):
            if cd_cur.class_id is "":
                cd_cur.class_id = cd_new.class_id
                cd_cur.save()


def update_timetable(date):
    current_center_schedule = CenterSchedule.objects.get(date=date)
    current_queryset = ClassDetail.objects.filter(center_schedule=current_center_schedule)
    latest_center_schedule_temp = CenterSchedule.objects.get(date='00000000')
    latest_queryset = ClassDetail.objects.filter(center_schedule=latest_center_schedule_temp)
    print(f'currently: {current_queryset.count()} items.')
    # if latest_queryset not in current_queryset, check for update, or add to current_queryset
    if latest_queryset.count() > 0:
        for detail_latest in latest_queryset:
            matching_item = current_queryset.filter(start_time=detail_latest.start_time,
                                                    class_name=detail_latest.class_name,
                                                    teacher=detail_latest.teacher,
                                                    location=detail_latest.location,
                                                    duration=detail_latest.duration)
            if not matching_item.exists():
                # check teacher
                if current_queryset.filter(start_time=detail_latest.start_time,
                                           class_name=detail_latest.class_name,
                                           location=detail_latest.location).exists():
                    detail_current = current_queryset.get(start_time=detail_latest.start_time,
                                                          class_name=detail_latest.class_name,
                                                          location=detail_latest.location)
                    print(f'replacing: {detail_current}')
                    detail_current.teacher = detail_latest.teacher
                    detail_current.duration = detail_latest.duration
                    detail_current.save()
                    print(f'with     : {detail_current}')
                # check class_name
                elif current_queryset.filter(location=detail_latest.location,
                                             start_time=detail_latest.start_time,
                                             teacher=detail_latest.teacher).exists():
                    detail_current = current_queryset.get(location=detail_latest.location,
                                                          start_time=detail_latest.start_time,
                                                          teacher=detail_latest.teacher)
                    print(f'replacing: {detail_current}')
                    detail_current.class_name = detail_latest.class_name
                    detail_current.duration = detail_latest.duration
                    detail_current.capacity = get_class_capacity(detail_latest.class_name)
                    detail_current.save()
                    print(f'with     : {detail_current}')
                # two classes changes time, same teacher, same class, same location
                # check start_time - more than 1 condition
                elif current_queryset.filter(location=detail_latest.location,
                                             class_name=detail_latest.class_name,
                                             teacher=detail_latest.teacher).exists():
                    # update start_time if only 1 item exists in both queryset
                    # and time difference is with 30 min
                    if current_queryset.filter(location=detail_latest.location,
                                               class_name=detail_latest.class_name,
                                               teacher=detail_latest.teacher).count() == 1 and \
                            latest_queryset.filter(location=detail_latest.location,
                                                   class_name=detail_latest.class_name,
                                                   teacher=detail_latest.teacher).count() == 1 and \
                            is_within_30_min(detail_latest, current_queryset):
                        # update detail_latest item to latest_queryset item
                        detail_current = current_queryset.get(location=detail_latest.location,
                                                              class_name=detail_latest.class_name,
                                                              teacher=detail_latest.teacher)
                        print(f'replacing: {detail_current}')
                        detail_current.start_time = detail_latest.start_time
                        detail_current.date_time_field = detail_latest.date_time_field
                        detail_current.save()
                        print(f'with     : {detail_current}')
                    # if class time change to more than 30min difference, create new
                    # extra class will be deleted in next check
                    else:
                        if not current_queryset.filter(location=detail_latest.location,
                                                       start_time=detail_latest.start_time,
                                                       class_name=detail_latest.class_name,
                                                       teacher=detail_latest.teacher).exists():
                            # create item
                            add_class = current_center_schedule.classdetail_set.create(
                                start_time=detail_latest.start_time,
                                class_id=detail_latest.class_id,
                                class_name=detail_latest.class_name,
                                teacher=detail_latest.teacher,
                                assistant=detail_latest.assistant,
                                location=detail_latest.location,
                                duration=detail_latest.duration,
                                date_time_field=detail_latest.date_time_field,
                                capacity=get_class_capacity(detail_latest.class_name),
                            )
                            print(f"adding   : {add_class}")
                # check class_name and teacher - more than 1 condition
                # assuming there can only be 2 classes at the same center at the same time
                # and only 1 class change, the other remains
                elif current_queryset.filter(location=detail_latest.location,
                                             start_time=detail_latest.start_time,
                                             duration=detail_latest.duration).exists():
                    sel_current_set = current_queryset.filter(location=detail_latest.location,
                                                              start_time=detail_latest.start_time,
                                                              duration=detail_latest.duration)
                    sel_latest_set = latest_queryset.filter(location=detail_latest.location,
                                                            start_time=detail_latest.start_time,
                                                            duration=detail_latest.duration)
                    # update class_name and teacher if only 1 item exists in both querryset
                    if sel_current_set.count() == 1 and sel_latest_set.count() == 1:
                        detail_current = current_queryset.get(location=detail_latest.location,
                                                              start_time=detail_latest.start_time,
                                                              duration=detail_latest.duration)
                        print(f'replacing: {detail_current}')
                        detail_current.class_name = detail_latest.class_name
                        detail_current.teacher = detail_latest.teacher
                        detail_current.duration = detail_latest.duration
                        detail_current.capacity = get_class_capacity(detail_latest.class_name)
                        detail_current.save()
                        print(f'with     : {detail_current}')
                    # match same start_time and location for update
                    else:
                        # issue can only be resolved if there are 2 update from 2 old one
                        # 1 new, 1 cancel with 2 old, or 2 new with 1 old can not be resolved
                        # there are simply not enough info to determind which is which
                        # in that case, app should notify users to check their selection
                        for latest in sel_latest_set:
                            # if not the same item from latest queryset
                            # making sure not comparing the same item
                            ### if not latest == detail_latest:
                            # 1. if only one existing item at the time and location
                            #    but two items at the time and location in latest set
                            #    create new
                            # 2. if two existing items at the time and location
                            #    and also two items in latest set
                            #    mate and update the one
                            if current_queryset.filter(
                                    location=detail_latest.location,
                                    start_time=detail_latest.start_time,
                                    duration=detail_latest.duration).count() == 1:
                                new_class = current_center_schedule.classdetail_set.create(
                                    start_time=detail_latest.start_time,
                                    class_id=detail_latest.class_id,
                                    class_name=detail_latest.class_name,
                                    teacher=detail_latest.teacher,
                                    assistant=detail_latest.assistant,
                                    location=detail_latest.location,
                                    duration=detail_latest.duration,
                                    date_time_field=detail_latest.date_time_field,
                                    capacity=get_class_capacity(detail_latest.class_name),
                                )
                                print(f"adding   : {new_class}")
                            else:
                                # making sure latest item with class name and teacher
                                # does not exist in current set
                                if not sel_current_set.filter(class_name=latest.class_name,
                                                              teacher=latest.teacher).exists():
                                    # assuming the other item with the same time and location does not change
                                    # loop through current set to find the one needs to be updated
                                    for current in sel_current_set:
                                        if not sel_latest_set.filter(class_name=current.class_name,
                                                                     teacher=current.teacher):
                                            print(f'replacing: {current} - test')
                                            current.class_name = latest.class_name
                                            current.teacher = latest.teacher
                                            current.duration = latest.duration
                                            current.capacity = get_class_capacity(latest.class_name)
                                            current.save()
                                            print(f'with     : {current} - test')
                                            break
                                    break
                else:
                    add_class = current_center_schedule.classdetail_set.create(
                        start_time=detail_latest.start_time,
                        class_id=detail_latest.class_id,
                        class_name=detail_latest.class_name,
                        teacher=detail_latest.teacher,
                        assistant=detail_latest.assistant,
                        location=detail_latest.location,
                        duration=detail_latest.duration,
                        date_time_field=detail_latest.date_time_field,
                        capacity=get_class_capacity(detail_latest.class_name),
                    )
                    print(f"adding   : {add_class}")
                current_queryset.update()
        # delete old items in current_queryset
        if not current_queryset.count() == latest_queryset.count():
            for detail_current in current_queryset:
                if not latest_queryset.filter(start_time=detail_current.start_time,
                                              class_name=detail_current.class_name,
                                              teacher=detail_current.teacher,
                                              location=detail_current.location,
                                              duration=detail_current.duration):
                    detail_current.delete()
                    print(f'deleting : {detail_current}')
        # ensuring current_queryset == latest_queryset
        current_queryset.update()
        for detail_current in current_queryset:
            if not latest_queryset.filter(start_time=detail_current.start_time,
                                          class_name=detail_current.class_name,
                                          location=detail_current.location,
                                          teacher=detail_current.teacher,
                                          duration=detail_current.duration).exists():
                print(f'{detail_current} - item from current '
                      f'schedule do not match with latest schedule.')
        for detail_latest in latest_queryset:
            if not current_queryset.filter(start_time=detail_latest.start_time,
                                           class_name=detail_latest.class_name,
                                           location=detail_latest.location,
                                           teacher=detail_latest.teacher,
                                           duration=detail_latest.duration).exists():
                print(f'{detail_latest} - item from latest '
                      f'schedule do not match with current schedule.')
        current_queryset.update()
        print(f'update to: {current_queryset.count()} items.')
    else:
        print('error     : latest timetable empty, update is not performed.')


@shared_task()
def schedule_update():
    date_start = 0
    if CenterSchedule.objects.count() > 0:
        date_difference = (datetime.strptime(
            CenterSchedule.objects.all().order_by('-date').first().date, '%Y%m%d'
        ) - datetime.today()).days + 2
    else:
        date_difference = 2
    request_cookies_browser = get_browser_cookies()
    if request_cookies_browser:
        # add CenterSchedule if database has less than 10 days of class schedule
        while date_difference < 10:
            if CenterSchedule.objects.count() > 0:
                last_sch_date = CenterSchedule.objects.all().order_by('-date').first().date
            else:
                last_sch_date = (datetime.today() - timedelta(days=1)).strftime("%Y%m%d")
            last_sch_date_str = datetime.strptime(last_sch_date, '%Y%m%d')
            new_sch_date_str = datetime.strftime(last_sch_date_str + timedelta(days=1), '%Y%m%d')
            print(f'creating : {new_sch_date_str} queryset...')
            center, is_created = Center.objects.get_or_create(type='yoga', city='hong kong')
            center.centerschedule_set.create(date=new_sch_date_str)
            date_difference = (datetime.strptime(new_sch_date_str, '%Y%m%d') -
                               datetime.today()).days + 2
            if date_difference == 10:
                break

        session = requests.Session()
        for cookies in request_cookies_browser:
            session.cookies.set(**cookies)
        try:
            # for now to last schedule
            for day in range(date_start, date_difference):
                print('==================================================')
                print('updating : ' + (datetime.today()+timedelta(days=day)).strftime('%Y%m%d') + ' schedule...')

                date_to_update = (datetime.today() + timedelta(days=day)).strftime('%Y%m%d')
                try:
                    get_latest_timetable(session, date_to_update)
                    update_timetable(date_to_update)
                finally:
                    if day < 3:
                        print(f"updating : class_id")
                        update_class_id(date_to_update)
                    clean_temp_table()
        finally:
            session.close()
            print('==================================================')
    else:
        print('error obtaining browser cookies, likely caused by reCAPTCHA...')
        print('==================================================')
