import time


def delayed_result():
    time.sleep(10)
    return 1


def failed_result():
    raise ValueError("sensitive native exception")
