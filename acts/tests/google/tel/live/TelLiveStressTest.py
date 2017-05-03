#!/usr/bin/env python3.4
#
#   Copyright 2017 - Google
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
"""
    Test Script for Telephony Stress Call Test
"""

import collections
import random
import time
from acts.test_utils.tel.TelephonyBaseTest import TelephonyBaseTest
from acts.test_utils.tel.tel_defines import WFC_MODE_WIFI_PREFERRED
from acts.test_utils.tel.tel_test_utils import active_data_transfer_test
from acts.test_utils.tel.tel_test_utils import call_setup_teardown
from acts.test_utils.tel.tel_test_utils import ensure_phone_default_state
from acts.test_utils.tel.tel_test_utils import ensure_phone_subscription
from acts.test_utils.tel.tel_test_utils import ensure_phones_idle
from acts.test_utils.tel.tel_test_utils import ensure_wifi_connected
from acts.test_utils.tel.tel_test_utils import hangup_call
from acts.test_utils.tel.tel_test_utils import run_multithread_func
from acts.test_utils.tel.tel_test_utils import set_wfc_mode
from acts.test_utils.tel.tel_test_utils import sms_send_receive_verify
from acts.test_utils.tel.tel_test_utils import mms_send_receive_verify
from acts.test_utils.tel.tel_test_utils import verify_incall_state
from acts.test_utils.tel.tel_voice_utils import is_phone_in_call_3g
from acts.test_utils.tel.tel_voice_utils import is_phone_in_call_2g
from acts.test_utils.tel.tel_voice_utils import is_phone_in_call_csfb
from acts.test_utils.tel.tel_voice_utils import is_phone_in_call_iwlan
from acts.test_utils.tel.tel_voice_utils import is_phone_in_call_volte
from acts.test_utils.tel.tel_voice_utils import phone_setup_csfb
from acts.test_utils.tel.tel_voice_utils import phone_setup_iwlan
from acts.test_utils.tel.tel_voice_utils import phone_setup_voice_3g
from acts.test_utils.tel.tel_voice_utils import phone_setup_voice_2g
from acts.test_utils.tel.tel_voice_utils import phone_setup_volte
from acts.utils import rand_ascii_str


class TelLiveStressTest(TelephonyBaseTest):
    def setup_class(self):
        super(TelLiveStressTest, self).setup_class()
        self.dut = self.android_devices[0]
        self.helper = self.android_devices[1]
        self.user_params["telephony_auto_rerun"] = False
        self.wifi_network_ssid = self.user_params.get(
            "wifi_network_ssid") or self.user_params.get("wifi_network_ssid_2g")
        self.wifi_network_pass = self.user_params.get(
            "wifi_network_pass") or self.user_params.get("wifi_network_pass_2g")
        self.phone_call_iteration = int(
            self.user_params.get("phone_call_iteration", 500))
        self.max_phone_call_duration = int(
            self.user_params.get("max_phone_call_duration", 600))
        self.max_sleep_time = int(self.user_params.get("max_sleep_time", 120))
        self.max_run_time = int(self.user_params.get("max_run_time", 1800))
        self.max_sms_length = int(self.user_params.get("max_sms_length", 1000))
        self.max_mms_length = int(self.user_params.get("max_mms_length", 160))

        return True

    def _setup_wfc(self):
        for ad in self.android_devices:
            if not ensure_wifi_connected(
                    ad.log,
                    ad,
                    self.wifi_network_ssid,
                    self.wifi_network_pass,
                    retry=3):
                ad.log.error("Phone Wifi connection fails.")
                return False
            ad.log.info("Phone WIFI is connected successfully.")
            if not set_wfc_mode(self.log, ad, WFC_MODE_WIFI_PREFERRED):
                ad.log.error("Phone failed to enable Wifi-Calling.")
                return False
            ad.log.info("Phone is set in Wifi-Calling successfully.")
            if not phone_idle_iwlan(self.log, self.ad):
                ad.log.error("Phone is not in WFC enabled state.")
                return False
            ad.log.info("Phone is in WFC enabled state.")
        return True

    def _setup_lte_volte_enabled(self):
        for ad in self.android_devices:
            if not phone_setup_volte(self.log, ad):
                ad.log.error("Phone failed to enable VoLTE.")
                return False
            ad.log.info("Phone VOLTE is enabled successfully.")
        return True

    def _setup_lte_volte_disabled(self):
        for ad in self.android_devices:
            if not phone_setup_csfb(self.log, ad):
                ad.log.error("Phone failed to setup CSFB.")
                return False
            ad.log.info("Phone VOLTE is disabled successfully.")
        return True

    def _setup_3g(self):
        for ad in self.android_devices:
            if not phone_setup_voice_3g(self.log, ad):
                ad.log.error("Phone failed to setup 3g.")
                return False
            ad.log.info("Phone RAT 3G is enabled successfully.")
        return True

    def _setup_2g(self):
        for ad in self.android_devices:
            if not phone_setup_voice_2g(self.log, ad):
                ad.log.error("Phone failed to setup 2g.")
                return False
            ad.log.info("RAT 2G is enabled successfully.")
        return True

    def _send_message(self, ads):
        selection = random.randrange(0, 2)
        message_type_map = {0: "SMS", 1: "MMS"}
        max_length_map = {0: self.max_sms_length, 1: self.max_mms_length}
        length = random.randrange(0, max_length_map[selection] + 1)
        text = rand_ascii_str(length)
        message_content_map = {0: [text], 1: [("Mms Message", text, None)]}
        message_func_map = {
            0: sms_send_receive_verify,
            1: mms_send_receive_verify
        }
        if not message_func_map[selection](self.log, ads[0], ads[1],
                                           message_content_map[selection]):
            self.log.error("%s of length %s from %s to %s fails",
                           message_type_map[selection], length, ads[0].serial,
                           ads[1].serial)
            return False
        else:
            self.log.info("%s of length %s from %s to %s succeed",
                          message_type_map[selection], length, ads[0].serial,
                          ads[1].serial)
            return False

    def _make_phone_call(self, ads):
        if not call_setup_teardown(
                self.log,
                ads[0],
                ads[1],
                ad_hangup=ads[random.randrange(0, 2)],
                wait_time_in_call=random.randrange(
                    1, self.max_phone_call_duration)):
            ads[0].log.error("Setup phone Call failed.")
            return False
        ads[0].log.info("Setup call successfully.")
        return True

    def _transfer_data(self):
        file_names = ["5MB", "10MB", "20MB", "50MB", "200MB", "512MB", "1GB"]
        selection = random.randrange(0, 7)
        return active_data_transfer_test(self.log, self.dut,
                                         file_names[selection])

    def call_test(self):
        failure = 0
        while time.time() < self.finishing_time:
            ads = [self.dut, self.helper]
            random.shuffle(ads)
            if not self._make_phone_call(ads):
                failure += 1
            self.dut.droid.goToSleepNow()
            time.sleep(random.randrange(0, self.max_sleep_time))
        return failure

    def message_test(self):
        failure = 0
        while time.time() < self.finishing_time:
            ads = [self.dut, self.helper]
            random.shuffle(ads)
            if not self._send_message(ads):
                failure += 1
            self.dut.droid.goToSleepNow()
            time.sleep(random.randrange(0, self.max_sleep_time))
        return failure

    def data_test(self):
        failure = 0
        while time.time() < self.finishing_time:
            if not self._transfer_data():
                failure += 1
            self.dut.droid.goToSleepNow()
            time.sleep(random.randrange(0, self.max_sleep_time))
        return failure

    def parallel_tests(self, setup_func=None):
        if setup_func and not setup_func():
            self.log.error("Test setup %s failed", setup_func.__name__)
            return False
        self.finishing_time = time.time() + self.max_run_time
        results = run_multithread_func(self.log, [(self.call_test, []), (
            self.message_test, []), (self.data_test, [])])
        self.log.info("Call failures: %s", results[0])
        self.log.info("Message failures: %s", results[1])
        self.log.info("Data failures: %s", results[2])
        for result in results:
            if result: return False

    """ Tests Begin """

    @TelephonyBaseTest.tel_test_wrap
    def test_default_parallel_stress(self):
        """ Default state stress test"""
        return self.parallel_tests()

    @TelephonyBaseTest.tel_test_wrap
    def test_lte_volte_stress(self):
        """ VoLTE on stress test"""
        return self.parallel_tests(setup_func=self._setup_lte_volte_enabled)

    @TelephonyBaseTest.tel_test_wrap
    def test_lte_volte_disabled_stress(self):
        """ LTE non-VoLTE stress test"""
        return self.parallel_tests(setup_func=self._setup_lte_volte_disabled)

    @TelephonyBaseTest.tel_test_wrap
    def test_wifi_calling_stress(self):
        """ Wifi calling on stress test"""
        return self.parallel_tests(setup_func=self._setup_wfc)

    @TelephonyBaseTest.tel_test_wrap
    def test_3g_stress(self):
        """ 3G stress test"""
        return self.parallel_tests(setup_func=self._setup_3g)

    @TelephonyBaseTest.tel_test_wrap
    def test_call_2g_stress(self):
        """ 2G call stress test"""
        return self.parallel_tests(setup_func=self._setup_2g)

    """ Tests End """