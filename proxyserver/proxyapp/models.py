from django.db import models

# Create your models here.

# Gospel
# secular
# romantic
# hip-hop
# reggae

"""
    channelName : "Hillsong Worship"
    currentTime : "0:14"
    duration: "6:17"
    savedAt : "2025-03-08T22:48:09.122Z"
    title : "Hosanna - Hillsong Worship"
    url : "https://www.youtube.com/watch?v=hnMevXQutyE&list=RDGfVd5x9W1Xc&index=15"
    videoId : "hnMevXQutyE"
"""

class Song(models.Model):
    CATEGORY_CHOICES = [
        ('Gospel', 'Gospel'),
        ('Secular', 'Secular'),
        ('Romantic', 'Romantic'),
        ('Hip-hop', 'Hip-hop'),
        ('Reggae', 'Reggae'),
    ]

    channelName = models.CharField(max_length=100)
    currentTime = models.CharField(max_length=10)
    duration = models.CharField(max_length=10)
    savedAt = models.DateTimeField()
    title = models.CharField(max_length=100)
    url = models.URLField()
    videoId = models.CharField(max_length=100)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    