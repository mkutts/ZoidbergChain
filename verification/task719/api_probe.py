"""Independent bounded diagnosis of the Windows event-loop socketpair hang."""
import faulthandler
import socket
import os
import threading


if __name__ == '__main__':
    watchdog = threading.Timer(12, lambda: os._exit(124))
    watchdog.daemon = True
    watchdog.start()
    faulthandler.dump_traceback_later(5)
    print('Creating stdlib default socketpair (no API, database or temporary files)', flush=True)
    pair = socket.socketpair()
    print('Default socketpair succeeded', flush=True)
    for sock in pair:
        sock.close()
    faulthandler.cancel_dump_traceback_later()
    watchdog.cancel()
