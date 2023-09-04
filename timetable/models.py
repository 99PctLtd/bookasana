from django.db import models
from django.urls import reverse
import uuid


class Center(models.Model):
    type = models.CharField(max_length=50)
    city = models.CharField(max_length=50, default='')

    def __str__(self):
        return self.city + " - " + self.type


class CenterSchedule(models.Model):
    center = models.ForeignKey(Center, on_delete=models.CASCADE)
    date = models.CharField(max_length=8, default='')

    def get_absolute_url(self):
        return reverse('schedule:ClassDetail-add')

    def __str__(self):
        return f"{self.center.city}, {self.center.type} - {self.date}, {str(self.classdetail_set.count())} classes"


class ClassDetail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, unique=True, editable=False)
    center_schedule = models.ForeignKey(CenterSchedule, on_delete=models.CASCADE)
    class_id = models.CharField(max_length=6, blank=True)
    start_time = models.CharField(max_length=5)
    class_name = models.CharField(max_length=100)
    teacher = models.CharField(max_length=50)
    assistant = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=100)
    duration = models.CharField(max_length=30)
    date_time_field = models.DateTimeField(null=True)
    capacity = models.PositiveSmallIntegerField(default=30)

    def get_absolute_url(self):
        return reverse('schedule:DailyDetail', kwargs={'CenterSchedule_date': self.center_schedule})

    def __str__(self):
        return f"{self.center_schedule.date} - {self.start_time} : " \
               f"{self.class_name}, {self.teacher} @ {self.location} - {self.duration}"
