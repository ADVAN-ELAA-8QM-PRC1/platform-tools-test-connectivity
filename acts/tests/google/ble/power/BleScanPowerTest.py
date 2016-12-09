#/usr/bin/env python3.4
#
# Copyright (C) 2016 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
"""
This test script exercises power test scenarios for different scan modes.
This test script was designed with this setup in mind:
Shield box one: Android Device and Monsoon tool box
"""

import json
import os

from acts.test_utils.bt.BluetoothBaseTest import BluetoothBaseTest
from acts.test_utils.bt.BleEnum import ScanSettingsScanMode
from acts.test_utils.bt.bt_test_utils import bluetooth_enabled_check
from acts.test_utils.bt.bt_test_utils import generate_ble_scan_objects
from acts.test_utils.bt.PowerBaseTest import PowerBaseTest


class BleScanPowerTest(PowerBaseTest):
    # Repetitions for scan and idle
    REPETITIONS_40 = 40
    REPETITIONS_360 = 360

    # Power measurement start time in seconds
    SCAN_START_TIME = 60
    # BLE scanning time in seconds
    SCAN_TIME_60 = 60
    SCAN_TIME_5 = 5
    # BLE no scanning time in seconds
    IDLE_TIME_30 = 30
    IDLE_TIME_5 = 5

    PMC_BASE_CMD = ("am broadcast -a com.android.pmc.BLESCAN --es ScanMode ")

    def setup_class(self):
        super(BleScanPowerTest, self).setup_class()

    def _measure_power_for_scan_n_log_data(self,
                                           scan_mode,
                                           scan_time,
                                           idle_time,
                                           repetitions,
                                           remove_idle_data=True):
        """utility function for power test with BLE scan.

        Steps:
        1. Prepare adb shell command
        2. Send the adb shell command to PMC
        3. PMC start first alarm to start scan
        4. After first alarm triggered it start the second alarm to stop scan
        5. Repeat the scan/idle cycle for the number of repetitions
        6. Save the power usage data into log file

        Args:
            scan_mode: Scan mode
            scan_time: Time duration for scanning
            idle_time: Time duration for idle after scanning
            repetitions:  The number of cycles of scanning/idle
            remove_idle_data: Boolean to indicate whether to include idle data
                              in average calculation

        Returns:
            None
        """

        first_part_msg = "%s%s --es StartTime %d --es ScanTime %d" % (
            self.PMC_BASE_CMD, scan_mode, self.SCAN_START_TIME, scan_time)
        msg = "%s --es NoScanTime %d --es Repetitions %d" % (
            first_part_msg, idle_time, repetitions)

        self.ad.log.info("Send broadcast message: %s", msg)
        self.ad.adb.shell(msg)
        # Start the power measurement
        sample_time = (scan_time + idle_time) * repetitions
        result = self.mon.measure_power(self.POWER_SAMPLING_RATE, sample_time,
                                        self.current_test_name,
                                        self.SCAN_START_TIME)

        if remove_idle_data:
            self.save_logs_for_power_test(result, scan_time, idle_time)
        else:
            self.save_logs_for_power_test(result, scan_time, 0)

    @BluetoothBaseTest.bt_test_wrap
    def test_power_for_scan_w_low_latency(self):
        """Test power usage when scan with low latency.

        Tests power usage when the device scans with low latency mode
        for 60 seconds and then idle for 30 seconds, repeat for 60 minutes
        where there are no advertisements.

        Steps:
        1. Prepare adb shell command
        2. Send the adb shell command to PMC
        3. PMC start first alarm to start scan
        4. After first alarm triggered it start the second alarm to stop scan
        5. Repeat the cycle for 60 minutes
        6. Save the power usage data into log file

        Expected Result:
        power consumption results

        TAGS: LE, Scanning, Power
        Priority: 3
        """
        self._measure_power_for_scan_n_log_data(
            ScanSettingsScanMode.SCAN_MODE_LOW_LATENCY.value,
            self.SCAN_TIME_60, self.IDLE_TIME_30, self.REPETITIONS_40)

    @BluetoothBaseTest.bt_test_wrap
    def test_power_for_scan_w_balanced(self):
        """Test power usage when scan with balanced mode.

        Tests power usage when the device scans with balanced mode
        for 60 seconds and then idle for 30 seconds, repeat for 60 minutes
        where there are no advertisements.

        Steps:
        1. Prepare adb shell command
        2. Send the adb shell command to PMC
        3. PMC start first alarm to start scan
        4. After first alarm triggered it start the second alarm to stop scan
        5. Repeat the cycle for 60 minutes
        6. Save the power usage data into log file

        Expected Result:
        power consumption results

        TAGS: LE, Scanning, Power
        Priority: 3
        """
        self._measure_power_for_scan_n_log_data(
            ScanSettingsScanMode.SCAN_MODE_BALANCED.value, self.SCAN_TIME_60,
            self.IDLE_TIME_30, self.REPETITIONS_40)

    @BluetoothBaseTest.bt_test_wrap
    def test_power_for_scan_w_low_power(self):
        """Test power usage when scan with low power.

        Tests power usage when the device scans with low power mode
        for 60 seconds and then idle for 30 seconds, repeat for 60 minutes
        where there are no advertisements.

        Steps:
        1. Prepare adb shell command
        2. Send the adb shell command to PMC
        3. PMC start first alarm to start scan
        4. After first alarm triggered it start the second alarm to stop scan
        5. Repeat the cycle for 60 minutes
        6. Save the power usage data into log file

        Expected Result:
        power consumption results

        TAGS: LE, Scanning, Power
        Priority: 3
        """
        self._measure_power_for_scan_n_log_data(
            ScanSettingsScanMode.SCAN_MODE_LOW_POWER.value, self.SCAN_TIME_60,
            self.IDLE_TIME_30, self.REPETITIONS_40)

    @BluetoothBaseTest.bt_test_wrap
    def test_power_for_intervaled_scans_w_balanced(self):
        """Test power usage when intervaled scans with balanced mode

        Tests power usage when the device perform multiple intervaled scans with
        balanced mode for 5 seconds each where there are no advertisements.

        Steps:
        1. Prepare adb shell command
        2. Send the adb shell command to PMC
        3. PMC start first alarm to start scan
        4. After first alarm triggered it starts the second alarm to stop scan
        5. After second alarm triggered it starts the third alarm to start scan
        6. Repeat the alarms until 360 scans are done
        7. Save the power usage data into log file

        Expected Result:
        power consumption results

        TAGS: LE, Scanning, Power
        Priority: 3
        """
        self._measure_power_for_scan_n_log_data(
            ScanSettingsScanMode.SCAN_MODE_BALANCED.value, self.SCAN_TIME_5,
            self.IDLE_TIME_5, self.REPETITIONS_360)

    @BluetoothBaseTest.bt_test_wrap
    def test_power_for_intervaled_scans_w_low_latency(self):
        """Test power usage when intervaled scans with low latency mode

        Tests power usage when the device perform multiple intervaled scans with
        low latency mode for 5 seconds each where there are no advertisements.

        Steps:
        1. Prepare adb shell command
        2. Send the adb shell command to PMC
        3. PMC start first alarm to start scan
        4. After first alarm triggered it starts the second alarm to stop scan
        5. After second alarm triggered it starts the third alarm to start scan
        6. Repeat the alarms until 360 scans are done
        7. Save the power usage data into log file

        Expected Result:
        power consumption results

        TAGS: LE, Scanning, Power
        Priority: 3
        """
        self._measure_power_for_scan_n_log_data(
            ScanSettingsScanMode.SCAN_MODE_LOW_LATENCY.value, self.SCAN_TIME_5,
            self.IDLE_TIME_5, self.REPETITIONS_360)

    @BluetoothBaseTest.bt_test_wrap
    def test_power_for_intervaled_scans_w_low_power(self):
        """Test power usage when intervaled scans with low power mode

        Tests power usage when the device perform multiple intervaled scans with
        low power mode for 5 seconds each where there are no advertisements.

        Steps:
        1. Prepare adb shell command
        2. Send the adb shell command to PMC
        3. PMC start first alarm to start scan
        4. After first alarm triggered it starts the second alarm to stop scan
        5. After second alarm triggered it starts the third alarm to start scan
        6. Repeat the alarms until 360 scans are done
        7. Save the power usage data into log file

        Expected Result:
        power consumption results

        TAGS: LE, Scanning, Power
        Priority: 3
        """
        self._measure_power_for_scan_n_log_data(
            ScanSettingsScanMode.SCAN_MODE_LOW_POWER.value, self.SCAN_TIME_5,
            self.IDLE_TIME_5, self.REPETITIONS_360)
