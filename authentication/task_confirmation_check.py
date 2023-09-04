from __future__ import absolute_import

from authentication.models import User
from bs4 import BeautifulSoup
from celery import shared_task
from datetime import datetime, date
from django.db.models import Count
import json
import requests
from account.models import (
    Cookie,
    CookieJar,
    MembershipRecord,
    Profile,
)
from booking.book_class import (
    get_headers,
    get_schedule_url,
    update_cookie_jar_time,
)


def account_validation(user, pure_login, pure_password):
    data = {
        'requiredtxtUserName': pure_login,
        'requiredtxtPassword': pure_password,
    }
    url_login = 'https://clients.mindbodyonline.com/Login?studioID=81&isLibAsync=true&isJson=true'
    client_session = requests.Session()
    for x in range(3):
        client_session.get(get_schedule_url(), headers=get_headers())
    response = client_session.post(url_login,
                                   headers=get_headers(), data=data)
    if json.loads(response.text)['json']['success']:
        profile = Profile.objects.get(user=user)
        cookie_jar, is_created = CookieJar.objects.get_or_create(profile=profile)
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
        client_session.close()
        return True
    else:
        return False


def cookie_setting(user, client_session):
    profile = Profile.objects.get(user=user)
    cookie_jar, is_created = CookieJar.objects.get_or_create(profile=profile)
    if is_created or (datetime.now() - cookie_jar.date_time_field).total_seconds() / 60 >= 30:
        # scrape new cookies if db cookies is older than 60 minutes
        data_login = {
            'requiredtxtUserName': user.pure_login,
            'requiredtxtPassword': user.pure_password,
        }
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
            soup = BeautifulSoup(response.content, "html.parser")
            cookie_jar.cookie_csrf = soup.find("input", {"name": "CSRFToken"}).get('value')
            cookie_jar.save()
    else:
        [client_session.cookies.set(c.cookie_name, c.cookie_value) for c in
         Cookie.objects.filter(cookie_jar=cookie_jar)]
        update_cookie_jar_time(cookie_jar)
    return client_session, cookie_jar


def parse_html_table(schedule):
    table_schedule = []
    for row in schedule.find_all('tr'):
        row_temp = []
        column_marker = 0
        columns = row.find_all('td')
        for column in columns:
            if column_marker == 1:
                if column.find("input", {
                    'class': "SignupButton"
                }) is None:
                    row_temp.append(column.get_text())
                    column_marker += 1
                else:
                    row_temp.append(column.find("input", {
                        'class': "SignupButton"
                    }).attrs['name'][3:])
                    column_marker += 1
            else:
                row_temp.append(column.get_text())
                column_marker += 1
        table_schedule.append(row_temp)
    # clear up first row
    del table_schedule[0]
    return table_schedule


def save_account_to_database(profile, account_table):
    # clean account_table
    for row in account_table:
        for i in range(8):
            row[i] = row[i].replace(u'\xa0', u'')
            row[i] = row[i].replace(u'\n', u'')
            row[i] = row[i].replace(u'\r', u'')
            row[i] = row[i].replace(u'\t', u'')
            row[i] = row[i].replace(u' ', u'')
    for row in account_table:
        paid_date = datetime.strptime(row[0], '%d/%m/%Y').strftime('%Y-%m-%d')
        exp_date = datetime.strptime(row[6], '%d/%m/%Y').strftime('%Y-%m-%d')
        profile.membershiprecord_set.get_or_create(paid_date=paid_date,
                                                   payment_ref=row[1],
                                                   amount=row[2],
                                                   description=row[3],
                                                   exp_date=exp_date,
                                                   available=True if row[7] == 'Yes' else False)
    # renew member can have two available memberships
    # ie. expire on 1 Feb (still available on the day),
    # new membership already available on 1 Feb
    # ==================================================
    # step 1: check if there are duplicate available records
    membership_record_set = MembershipRecord.objects.filter(profile=profile, available=True)
    dup_membership = membership_record_set.values('description').annotate(Count('id')).order_by().filter(id__count__gt=1)
    if dup_membership:
        # looping through yoga and fitness membership
        for dup_m in dup_membership:
            dup_description = dup_m['description']
            for m_r in membership_record_set.filter(description=dup_description).order_by('-exp_date')[1:]:
                m_r.available = False
                m_r.save()
        print(f'{profile.user.username} - successfully updated membership record.')
    # step 2: check exp_date
    membership_record_update = MembershipRecord.objects.filter(profile=profile, available=True)
    for membership in membership_record_update:
        if membership.exp_date < date.today():
            print(f'{profile.user.username} - removing invalid membership : '
                  f'{membership_record_set[0].description}...')
            membership_record_set[0].available = False
            membership_record_set[0].save()


def set_current_membership(profile):
    for membership_record in MembershipRecord.objects.filter(profile=profile,
                                                             available=True):
        if "yoga" or "cyp" or "mc5" or "lin" or "lpy" or "pen" or "pp" or \
                "sou" or "sts" in membership_record.description.lower():
            set_yoga_membership(profile, membership_record)
        elif "fit" or "lpf" in membership_record.description.lower():
            set_fitness_membership(profile, membership_record)
        elif "grandopening" in membership_record.description.lower():
            set_special_membership(profile, membership_record)


def set_fitness_membership(profile, membership_record):
    profile.membership_exp_fitness = membership_record.exp_date
    profile.membership_ref_fitness = membership_record.payment_ref
    profile.membership_type_fitness = membership_record.description
    profile.save()


def set_profile(profile, client_info):
    client_address = ''
    if client_info.find("div", attrs={"class": "infoValue",
                                      "id": "address"}):
        client_address += client_info.find("div",
                                           attrs={"class": "infoValue",
                                                  "id": "address"}).get_text() + ', '
    if client_info.find("div", attrs={"class": "infoValue", "id": "cityStateZip"}):
        client_address += client_info.find("div",
                                           attrs={"class": "infoValue",
                                                  "id": "cityStateZip"}).get_text() + ', '
    if client_info.find("div", attrs={"class": "infoValue", "id": "country"}):
        client_address += client_info.find("div",
                                           attrs={"class": "infoValue",
                                                  "id": "country"}).get_text()
    profile.memberinfo_set.get_or_create(
        name=client_info.find("div", attrs={"class": "infoValue",
                                            "id": "name"}).get_text(),
        email=client_info.find("div", attrs={"class": "infoValue",
                                             "id": "email"}).get_text(),
        address=client_address,
        birthday=datetime.strptime(
            client_info.find("div", attrs={"class": "infoValue",
                                           "id": "birthdate"}).get_text(),
            '%d/%m/%Y').strftime('%Y-%m-%d'),
        cellphone=client_info.find("div", attrs={"class": "infoValue",
                                                 "id": "cellphone"}).get_text(),
    )


def set_special_membership(profile, membership_record):
    profile.membership_exp_special = membership_record.exp_date
    profile.membership_ref_special = membership_record.payment_ref
    profile.membership_type_special = membership_record.description
    profile.save()


def set_yoga_membership(profile, membership_record):
    profile.membership_exp_yoga = membership_record.exp_date
    profile.membership_ref_yoga = membership_record.payment_ref
    profile.membership_type_yoga = membership_record.description
    profile.save()


# get cookies | extracted to cookie_setting
@shared_task
def parse_validated_account(uid):
    user = User.objects.get(pk=uid)
    client_session = requests.Session()
    client_session, cookie_jar = cookie_setting(user, client_session)
    # set csrf
    response = client_session.get(
        'https://clients.mindbodyonline.com/ASP/my_ph.asp',
        headers=get_headers(),
    )
    soup = BeautifulSoup(response.content, "html.parser")
    cookie_jar.cookie_csrf = soup.find("input", {"name": "CSRFToken"}).get('value')
    cookie_jar.save()
    # parse client membership account
    client_account = soup.find("table", {"class": "myInfoTable"})
    account_table = parse_html_table(client_account)
    # save account table to database
    save_account_to_database(user.profile, account_table)
    set_current_membership(user.profile)
    # parse client id
    response = client_session.get('https://clients.mindbodyonline.com/ASP/main_info.asp',
                                  headers=get_headers())
    soup = BeautifulSoup(response.content, "html.parser")
    user.profile.client_id = soup.find("input", {"id": 'thisClientID'}).get('value')
    user.profile.save()
    # parse client profile
    client_info = soup.find(id='StoredPersonalInfo')
    set_profile(user.profile, client_info)
    client_session.close()