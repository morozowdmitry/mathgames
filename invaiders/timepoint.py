import datetime


def string2date(date_string):
    if date_string:
        date_time_obj = datetime.datetime.strptime(date_string, '%d/%m/%Y %H:%M:%S')
    else:
        date_time_obj = datetime.datetime(year=2020, month=10, day=31)
    return date_time_obj


def date2string(date_time_obj):
    return date_time_obj.strftime("%m/%d/%Y %H:%M:%S")
