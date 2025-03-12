# Generated by Django 5.0.1 on 2025-03-09 14:31

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Song',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('channelName', models.CharField(max_length=100)),
                ('currentTime', models.CharField(max_length=10)),
                ('duration', models.CharField(max_length=10)),
                ('savedAt', models.DateTimeField()),
                ('title', models.CharField(max_length=100)),
                ('url', models.URLField()),
                ('videoId', models.CharField(max_length=100)),
                ('category', models.CharField(choices=[('Gospel', 'Gospel'), ('Secular', 'Secular'), ('Romantic', 'Romantic'), ('Hip-hop', 'Hip-hop'), ('Reggae', 'Reggae')], max_length=10)),
            ],
        ),
    ]
