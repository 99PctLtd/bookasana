from bs4 import BeautifulSoup
from datetime import datetime
import json
import requests

from account.models import Profile, MembershipRecord, MemberInfo
from authentication.models import User


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


def save_to_database(profile, account_table):
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
        new_pro, created = profile.membershiprecord_set.get_or_create(paid_date=paid_date,
                                                                      payment_ref=row[1],
                                                                      amount=row[2],
                                                                      description=row[3],
                                                                      exp_date=exp_date,
                                                                      available=True if row[7] == 'Yes' else False)


def set_current_membership(profile):
    for membership_record in MembershipRecord.objects.filter(profile=profile,
                                                             available=True):
        if "yoga" or "pen" or "sou" in membership_record.description.lower():
            set_yoga_membership(profile, membership_record)
        elif "fit" in membership_record.description.lower():
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


def main(username):
    user = User.objects.get(username=username)
    profile = Profile.objects.get(user=user)

    url_schedule = f"https://clients.mindbodyonline.com/classic/mainclass?studioid=81" \
                   f"&tg=&vt=&lvl=&stype=&view=&trn=0&page=&catid=&prodid=&date=" \
                   f"{datetime.today().strftime('%m')}%2f{datetime.today().strftime('%d')}" \
                   f"%2f{datetime.today().strftime('%Y')}&classid=0&prodGroupId=&sSU=" \
                   f"&optForwardingLink=&qParam=&justloggedin=&nLgIn=&pMode=0"
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0'
    }
    data = {
        'requiredtxtUserName': user.pure_login,
        'requiredtxtPassword': user.pure_password,
    }

    print(f'{username}: getting cookies...')
    client_session = requests.Session()
    for x in range(3):
        client_session.get(url_schedule, headers=headers)
    response = client_session.post('https://clients.mindbodyonline.com/Login?studioID=81&isLibAsync=true&isJson=true',
                                   headers=headers, data=data)

    # json response only available with requests session
    if json.loads(response.text)['json']['success']:
        print(f'login successfully with {username} account info...')
        # parse client membership account
        # ==================================================
        print(f'{username}: setting membership account info...')
        response = client_session.get('https://clients.mindbodyonline.com/ASP/my_ph.asp',
                                      headers=headers)
        soup = BeautifulSoup(response.text, 'lxml')
        client_account = soup.find("table", {"class": "myInfoTable"})
        account_table = parse_html_table(client_account)

        # taking account table and save to database
        save_to_database(user.profile, account_table)

        print(f'{username}: setting current membership info...')
        set_current_membership(profile)

        # parse client id
        # ==================================================
        print(f'{username}: setting client id...')
        response = client_session.get('https://clients.mindbodyonline.com/ASP/main_info.asp',
                                      headers=headers)
        soup = BeautifulSoup(response.text, 'lxml')
        user.profile.client_id = soup.find("input", {"id": 'thisClientID'}).get('value')
        user.profile.save()

        # parse client profile
        # ==================================================
        print(f'{username}: setting client profile info...')
        client_info = soup.find(id='StoredPersonalInfo')
        set_profile(user.profile, client_info)

        client_session.close()
        print()
    else:
        print(f'login failed with provided login info, please check try again.')


if __name__ == '__main__':
    main()

# main('admin_ks')
