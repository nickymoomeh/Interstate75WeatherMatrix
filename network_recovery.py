"""Small cooperative Wi-Fi/NTP scheduler; all intervals use monotonic ticks."""
import network
import time
import ntptime

class Recovery:
    def __init__(self, ssid, password):
        self.ssid, self.password = ssid, password
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.connect_started = None
        self.next_connect = time.ticks_ms()
        self.next_ntp = time.ticks_ms()
        self.synced = False
        self.was_connected = False

    def poll(self, now):
        connected = self.wlan.isconnected()
        recovered = connected and not self.was_connected
        self.was_connected = connected
        if connected:
            self.connect_started = None
            if time.ticks_diff(now, self.next_ntp) >= 0:
                # Set the retry deadline BEFORE attempting NTP, including daily failures.
                self.next_ntp = time.ticks_add(now, 300000)
                try:
                    ntptime.timeout = 2
                    ntptime.settime()
                    self.synced = True
                    self.next_ntp = time.ticks_add(time.ticks_ms(), 86400000)
                except Exception as error:
                    print("NTP retry deferred:", error)
        elif self.connect_started is not None:
            if time.ticks_diff(now, self.connect_started) >= 25000:
                try:
                    self.wlan.disconnect()
                    self.wlan.active(False)
                    self.wlan.active(True)
                except Exception:
                    pass
                self.connect_started = None
                self.next_connect = time.ticks_add(now, 30000)
        elif time.ticks_diff(now, self.next_connect) >= 0:
            self.next_connect = time.ticks_add(now, 30000)
            try:
                self.wlan.connect(self.ssid, self.password)
                self.connect_started = now
            except Exception as error:
                print("Wi-Fi retry deferred:", error)
        return connected, recovered
