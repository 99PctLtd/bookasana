import sendgrid
from decouple import config

SEND_GRID_API_KEY = config('SEND_GRID_API_KEY',)


def send_grid_email(content, **kwargs):
    if kwargs.get("activation"):
        # activation template id
        temp_id = "d-67370d89ce694b2a948219e9d81f6a33"
    elif kwargs.get("password_reset"):
        # password reset template id
        temp_id = "d-004c97a325744a0790ce3e7919e13466"
    else:
        temp_id = "none"
    email_user = content['user'].pure_login
    first_name = content['user'].first_name
    username = content['user'].username
    url_uid_token = f"{content['protocol']}://{content['domain']}{content['uid_token']}"
    sg = sendgrid.SendGridAPIClient(apikey=SEND_GRID_API_KEY)
    data = {
        "personalizations": [
            {
                "to": [
                    {
                        "email": email_user,
                    }
                ],
                "dynamic_template_data": {
                    'first_name': first_name,
                    'username': username,
                    'url_uid_token': str(url_uid_token),
                }
            }
        ],
        "from": {
            "email": "admin@bookasana.com",
            "name": "Admin",
        },
        "template_id": temp_id,
    }
    sg.client.mail.send.post(request_body=data)