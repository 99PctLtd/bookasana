import json
from time import sleep
from asgiref.sync import async_to_sync
from channels.generic.websocket import (
    WebsocketConsumer
)


class NotificationConsumer(WebsocketConsumer):

    def connect(self):
        self.user_name = self.scope['user'].username

        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.user_name,
            self.channel_name
        )

        self.accept()

    def disconnect(self, close_code):
        # Leave room group
        async_to_sync(self.channel_layer.group_discard)(
            self.user_name,
            self.channel_name
        )

    def send_notification(self, text_data):
        # Send message to room group
        self.send(text_data=json.dumps({
            'text': text_data['text']['message'],
            'level': text_data['text']['level'],
        }))
