from threading import current_thread


def get_thread_num() -> int:
    if current_thread().name == 'MainThread':
        return 0
    else:
        return int(current_thread().name.split('-')[1].split('_')[1])
