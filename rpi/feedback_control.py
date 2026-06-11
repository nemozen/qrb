#!/usr/bin/python3
'''Feedback control loop: reads temperature from the sensor, computes
feedback signal (equivalent to a temperature forecast) and activates
the pump control (toggle_relay) to stay below threshold temperature.

Usage:

./feedback_control.py > feedback_control.log 2>&1 &
'''

import numpy as np
import time

import qrb_logging
import relay_webapp

DRY_RUN=False  # if True, no activation, reading and simulation only
SENSOR_PERIOD = 60

# Feedback control parameters
WINDOW = 3600            # look back to compute derivative and integral
THRESHOLD_TEMP = 25      # target to stay under

MAX_ACTIVATIONS_PER_DAY = 48
DAY_LENGTH = 24*60*60
MAX_ACTIVATION_DURATION = 300
MIN_ACTIVATION_DURATION = 32  # time for pump to start having an effect
MTB_ACTIVATIONS = 900    # min time between activations (1/max control freq)

TEMP_BETA=0.66           # °C ~smallest achievable temp change
DURATION_ALPHA=37        # sec/°C duration per temp change
Kp = 1.0
Kd = MTB_ACTIVATIONS     # derivative coeff = look ahead time ~ 1/control_freq
Ki = 1.0/WINDOW


def integral(x, y):
    return np.sum(y[:-1] * np.diff(x))


def slope(x, y):
    '''Least squares regression: y = a*x + b. Returns a.'''
    X = np.vstack([x - x[0], np.ones(len(x))]).T
    a, b = np.linalg.lstsq(X, y, rcond=None)[0]
    return a


def slice_to_window(time_series, value_series, window_start):
    n = 0
    while n < len(time_series) and time_series[n] < window_start:
        n += 1
    return time_series[n:], value_series[n:]


def main(my_logger):
    errors_history = np.array([])
    time_history = np.array([])
    activation_history = []
    t = None

    while True:
        if t: # don't sleep on the first iteration
            time.sleep(SENSOR_PERIOD)
        t = time.monotonic()
        temperature, humidity = relay_webapp.read_sensor()
        if temperature is None:
            my_logger.error("read_sensor failed")
            continue
        time_history, errors_history = slice_to_window(
            np.append(time_history, t),
            np.append(errors_history, temperature - THRESHOLD_TEMP),
            t-WINDOW)
        if len(time_history) < 5:
            continue

        # Control signal u is PID (proportional, integral, derivative)
        # of temperature error, and equivalent to desired temp change
        u = Kp * errors_history[-1] + \
            Kd * slope(time_history, errors_history) + \
            Ki * integral(time_history, errors_history)
        my_logger.debug({"message": "Control signal",
                         "Temperature": temperature,
                         "Humidity": humidity,
                         "Control": u})

        if u < TEMP_BETA:
            continue

        while activation_history and activation_history[0] < t-DAY_LENGTH:
            activation_history.pop(0)

        if len(activation_history) >= MAX_ACTIVATIONS_PER_DAY:
            my_logger.debug({"message": "Skip. Daily max."})
            continue

        if activation_history and t - activation_history[-1] < MTB_ACTIVATIONS:
            my_logger.debug({"message": "Skip. Max frequency."})
            continue

        duration = DURATION_ALPHA * u + MIN_ACTIVATION_DURATION
        duration = int(min(MAX_ACTIVATION_DURATION, duration))
        my_logger.info({"message": "Activate", "duration": duration})
        if not DRY_RUN:
            relay_webapp.toggle_relay(duration)
        activation_history.append(t)


if __name__ == '__main__':
    my_logger = qrb_logging.get_logger("rpi.feedback_control")
    try:
        main(my_logger)
    except Exception as e:
        my_logger.error(e)
        raise e
