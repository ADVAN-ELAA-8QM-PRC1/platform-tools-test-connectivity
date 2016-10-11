#!/usr/bin/python3.4
#
#   Copyright 2016 - The Android Open Source Project
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

import json
import pprint
import re
import queue
import statistics

from acts import asserts
from acts import base_test
from acts.signals import generated_test
from acts.test_utils.net import connectivity_const as con_const
from acts.test_utils.net import nsd_const as nsd_const
from acts.test_utils.wifi import wifi_test_utils as wutils
from acts.test_utils.wifi import wifi_nan_const as nan_const

# arbitrary timeout for events
EVENT_TIMEOUT = 30

class WifiNanManagerTest(base_test.BaseTestClass):
    # configuration parameters used by tests
    publish_config = {"ServiceName": "GoogleTestServiceX",
                      "ServiceSpecificInfo": "Data XYZ",
                      "MatchFilter": {"int0": 14, "data0": "MESSAGE_ALL"},
                      "PublishType": 0, "PublishCount": 0, "TtlSec": 0};
    subscribe_config = {"ServiceName": "GoogleTestServiceX",
                        "ServiceSpecificInfo": "Data ABC",
                        "MatchFilter": {"int0": 14, "data0": "MESSAGE_ALL"},
                        "SubscribeType": 0, "SubscribeCount": 0, "TtlSec": 0,
                        "MatchStyle": 0};
    rtt_24_20 = {"deviceType": 5, "requestType": 2, "frequency": 2437,
                 "channelWidth": 0, "centerFreq0": 2437, "centerFreq1": 0,
                 "numberBurst": 0, "numSamplesPerBurst": 5,
                 "numRetriesPerMeasurementFrame": 3, "numRetriesPerFTMR": 3,
                 "LCIRequest": False, "LCRRequest": False, "burstTimeout": 15,
                 "preamble": 2, "bandwidth": 4};
    rtt_50_40 = {"deviceType": 5, "requestType": 2, "frequency": 5200,
                 "channelWidth": 1, "centerFreq0": 5190, "centerFreq1": 0,
                 "numberBurst": 0, "numSamplesPerBurst": 5,
                 "numRetriesPerMeasurementFrame": 3, "numRetriesPerFTMR": 3,
                 "LCIRequest": False, "LCRRequest": False, "burstTimeout": 15,
                 "preamble": 2, "bandwidth": 8};
    rtt_50_80 = {"deviceType": 5, "requestType": 2, "frequency": 5200,
                 "channelWidth": 2, "centerFreq0": 5210, "centerFreq1": 0,
                 "numberBurst": 0, "numSamplesPerBurst": 5,
                 "numRetriesPerMeasurementFrame": 3, "numRetriesPerFTMR": 3,
                 "LCIRequest": False, "LCRRequest": False, "burstTimeout": 15,
                 "preamble": 4, "bandwidth": 16};
    network_req = {"TransportType": 5};
    nsd_service_info = {"serviceInfoServiceName": "sl4aTestNanIperf",
                        "serviceInfoServiceType": "_simple-tx-rx._tcp.",
                        "serviceInfoPort": 2257};

    def setup_test(self):
        self.msg_id = 10
        for ad in self.android_devices:
            asserts.assert_true(
                wutils.wifi_toggle_state(ad, True),
                "Failed enabling Wi-Fi interface")
            nan_usage_enabled = ad.droid.wifiIsNanAvailable()
            if not nan_usage_enabled:
                self.log.info('NAN not enabled. Waiting for %s',
                              nan_const.BROADCAST_WIFI_NAN_AVAILABLE)
                try:
                    ad.ed.pop_event(nan_const.BROADCAST_WIFI_NAN_AVAILABLE,
                                    EVENT_TIMEOUT)
                    self.log.info(nan_const.BROADCAST_WIFI_NAN_AVAILABLE)
                except queue.Empty:
                    asserts.fail('Timed out while waiting for %s' %
                                 nan_const.BROADCAST_WIFI_NAN_AVAILABLE)

    def teardown_test(self):
        for ad in self.android_devices:
            ad.droid.wifiNanDestroyAll()
    #         asserts.assert_true(
    #             wutils.wifi_toggle_state(ad, False),
    #             "Failed disabling Wi-Fi interface")

    def extract_stats(self, data, results, key_prefix, log_prefix):
        """Extract statistics from the data, store in the dict dictionary, and
        output to the info log.

        Args:
            data: A list containing the data to be analyzed.
            results: A dictionary into which to place the statistics.
            key_prefix: A string prefix to use for the dict keys storing the
                        extracted stats.
            log_prefix: A string prefix to use for the info log.
            include_data: If True includes the raw data in the dictionary,
                          otherwise just the stats.
        """
        num_samples = len(data)
        results['%s_num_samples' % key_prefix] = num_samples

        if not data:
            return

        data_min = min(data)
        data_max = max(data)
        data_mean = statistics.mean(data)

        results['%s_min' % key_prefix] = data_min
        results['%s_max' % key_prefix] = data_max
        results['%s_mean' % key_prefix] = data_mean
        results['%s_raw_data' % key_prefix] = data

        if num_samples > 1:
            data_stdev = statistics.stdev(data)
            results['%s_stdev' % key_prefix] = data_stdev
            self.log.info(
                '%s: num_samples=%d, min=%.2f, max=%.2f, mean=%.2f, stdev=%.2f',
                log_prefix, num_samples, data_min, data_max, data_mean,
                data_stdev)
        else:
            self.log.info('%s: num_samples=%d, min=%.2f, max=%.2f, mean=%.2f',
                          log_prefix, num_samples, data_min, data_max,
                          data_mean)

    def get_interface_mac(self, device, interface):
        """Get the HW MAC address of the specified interface.

        Returns the HW MAC address or raises an exception on failure.

        Args:
            device: The 'AndroidDevice' on which to query the interface.
            interface: The name of the interface to query.

        Returns:
            mac: MAC address of the interface.
        """
        out = device.adb.shell("ifconfig %s" % interface)
        completed = out.decode('utf-8').strip()
        res = re.match(".* HWaddr (\S+).*", completed, re.S)
        asserts.assert_true(res, 'Unable to obtain MAC address for interface %s'
                            % interface)
        return res.group(1)

    def get_interface_ipv6_link_local(self, device, interface):
        """Get the link-local IPv6 address of the specified interface.

        Returns the link-local IPv6 address of the interface or raises an
        exception on failure.

        Args:
            device: The 'AndroidDevice' on which to query the interface.
            interface: The name of the interface to query.

        Returns:
            addr: link-local IPv6 address of the interface.
        """
        out = device.adb.shell("ifconfig %s" % interface)
        completed = out.decode('utf-8').strip()
        res = re.match(".*inet6 addr: (\S+)/64 Scope: Link.*", completed, re.S)
        asserts.assert_true(res,
                            'Unable to obtain IPv6 link-local for interface %s'
                            % interface)
        return res.group(1)

    def exec_connect(self, device, name):
        """Executes the NAN connection creation operation.

        Creates a NAN connection (client) and waits for a confirmation event
        of success. Raise test failure signal if no such event received.

        Args:
            device: The 'AndroidDevice' on which to set up the connection.
            name: An arbitary name used for logging.
        """
        session_id = device.droid.wifiNanAttach()
        try:
            event = device.ed.pop_event(nan_const.EVENT_CB_ON_ATTACHED, EVENT_TIMEOUT)
            self.log.info('%s: %s', nan_const.EVENT_CB_ON_ATTACHED, event['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on %s' %
                         (nan_const.EVENT_CB_ON_ATTACHED, name))
        self.log.debug(event)
        return session_id

    def reliable_tx(self, device, session_id, peer, msg):
        """Sends a NAN message.

        Sends a message to the peer and waits for success confirmation. Raises
        an exception on failure or timeout.

        The message is sent using the MAX retransmission count.

        Args:
            device: The 'AndroidDevice' on which to send the message.
            session_id: The session ID context from which to send the message.
                This is the value returned by wifiNanPublish() or
                wifiNanSubscribe().
            peer: The peer ID to send the message to. Obtained through a match
                or a received message.
            msg: The message to be transmitted to the peer.
        """
        events_regex = '%s|%s' % (nan_const.SESSION_CB_ON_MESSAGE_SEND_FAILED,
                                  nan_const.SESSION_CB_ON_MESSAGE_SENT)
        self.msg_id = self.msg_id + 1

        while True:
            try:
                device.droid.wifiNanSendMessage(session_id, peer, self.msg_id, msg,
                                                nan_const.MAX_TX_RETRIES)
                events = device.ed.pop_events(events_regex, EVENT_TIMEOUT)
            except queue.Empty:
                asserts.fail('Timed out while waiting for %s', events_regex)

            for event in events:
                self.log.info('%s: %s', event['name'], event['data'])
                if event['data']['messageId'] == self.msg_id:
                    asserts.assert_equal(event['name'], nan_const.SESSION_CB_ON_MESSAGE_SENT,
                                         'Failed (re)transmission')
                    return

    def exec_rtt(self, device, session_id, peer_id, rtt_param, label,
                 repeat_count):
        """Executes an RTT operation.

        Args:
            device: The 'AndroidDevice' on which to send the message.
            session_id: The session ID context from which to send the message.
                This is the value returned by wifiNanPublish() or
                wifiNanSubscribe().
            peer_id: The peer ID to send the message to. Obtained through a
                match or a received message.
            rtt_param: RTT session parameters.
            msg: Message/tag describing RTT experiment.
            repeat_count: Number of RTT measurements to execute.
        """
        rtt_param['bssid'] = peer_id
        rtt_stats = {
            'failure_codes': {},
            'distance': {
                'sum': 0,
                'num_samples': 0
            }
        }
        for i in range(repeat_count):
            device.droid.wifiNanStartRanging(0, session_id, [rtt_param])

            events_regex = '%s|%s|%s' % (nan_const.RTT_LISTENER_CB_ON_SUCCESS,
                                         nan_const.RTT_LISTENER_CB_ON_FAILURE,
                                         nan_const.RTT_LISTENER_CB_ON_ABORT)
            try:
                events_pub_range = device.ed.pop_events(events_regex,
                                                        EVENT_TIMEOUT)
                for event in events_pub_range:
                    self.log.debug('%s: %s: %s', label, event['name'],
                                   event['data'])
                    results = event['data']['Results']
                    for rtt_result in results:
                        rtt_status = rtt_result['status']
                        if rtt_status == 0:
                            distance = rtt_result['distance']
                            self.log.info('%s: distance=%d', label, distance)
                            rtt_stats['distance']['sum'] = (
                                rtt_stats['distance']['sum'] + distance)
                            rtt_stats['distance']['num_samples'] = (
                                rtt_stats['distance']['num_samples'] + 1)
                        else:
                            self.log.info('%s: status=%d', label, rtt_status)
                            if rtt_status not in rtt_stats['failure_codes']:
                                rtt_stats['failure_codes'][rtt_status] = 0
                            rtt_stats['failure_codes'][rtt_status] = (
                                rtt_stats['failure_codes'][rtt_status] + 1)
            except queue.Empty:
                self.log.info('%s: Timed out while waiting for RTT events %s',
                              label, events_regex)
        self.log.info('%s:\n\tParam: %s\n\tRTT statistics: %s', label,
                      rtt_param, rtt_stats)

    def run_nan_discovery_session(self, discovery_config):
        """Perform NAN configuration, discovery, and message exchange.

        Configuration: 2 devices, one acting as Publisher (P) and the
        other as Subscriber (S)

        Logical steps:
          * P & S initiate NAN clustering (if not already up)
          * P & S wait for NAN connection confirmation
          * P starts publishing
          * S starts subscribing
          * S waits for a match (discovery) notification
          * S sends a message to P, confirming that sent successfully
          * P waits for a message and confirms that received (uncorrupted)
          * P sends a message to S, confirming that sent successfully
          * S waits for a message and confirms that received (uncorrupted)

        Args:
            discovery_configs: {'Title': description,
                'PublishConfig': publish_config,
                'SubscribeConfig': subscribe_config}

        Returns:
            True if discovery succeeds, else false.
        """
        # Configure Test
        self.publisher = self.android_devices[0]
        self.subscriber = self.android_devices[1]

        sub2pub_msg = "How are you doing? 你好嗎？"
        pub2sub_msg = "Doing ok - thanks! 做的不錯 - 謝謝！"

        # Start Test
        pub_connect_id = self.exec_connect(self.publisher, "publisher")
        sub_connect_id = self.exec_connect(self.subscriber, "subscriber")

        # Configuration
        publish_config = discovery_config['PublishConfig']
        subscribe_config = discovery_config['SubscribeConfig']
        self.log.debug('Publish config=%s, Subscribe config=%s', publish_config, subscribe_config)

        pub_id = self.publisher.droid.wifiNanPublish(pub_connect_id, publish_config)
        sub_id = self.subscriber.droid.wifiNanSubscribe(sub_connect_id, subscribe_config)

        try:
            event_sub_match = self.subscriber.ed.pop_event(
                nan_const.SESSION_CB_ON_SERVICE_DISCOVERED, EVENT_TIMEOUT)
            self.log.info('%s: %s', nan_const.SESSION_CB_ON_SERVICE_DISCOVERED,
                          event_sub_match['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on Subscriber' %
                         nan_const.SESSION_CB_ON_SERVICE_DISCOVERED)
        self.log.debug(event_sub_match)

        self.reliable_tx(self.subscriber, sub_id,
                         event_sub_match['data']['peerId'], sub2pub_msg)

        try:
            event_pub_rx = self.publisher.ed.pop_event(
                nan_const.SESSION_CB_ON_MESSAGE_RECEIVED, EVENT_TIMEOUT)
            self.log.info('%s: %s',
                          nan_const.SESSION_CB_ON_MESSAGE_RECEIVED,
                          event_pub_rx['data'])
            asserts.assert_equal(event_pub_rx['data']['messageAsString'],
                                 sub2pub_msg,
                                 "Subscriber -> publisher message corrupted")
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on publisher' %
                         nan_const.SESSION_CB_ON_MESSAGE_RECEIVED)

        self.reliable_tx(self.publisher, pub_id,
                         event_pub_rx['data']['peerId'], pub2sub_msg)

        try:
            event_sub_rx = self.subscriber.ed.pop_event(
                nan_const.SESSION_CB_ON_MESSAGE_RECEIVED, EVENT_TIMEOUT)
            self.log.info('%s: %s',
                          nan_const.SESSION_CB_ON_MESSAGE_RECEIVED,
                          event_sub_rx['data'])
            asserts.assert_equal(event_sub_rx['data']['messageAsString'],
                                 pub2sub_msg,
                                 "Publisher -> subscriber message corrupted")
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on subscriber' %
                         nan_const.SESSION_CB_ON_MESSAGE_RECEIVED)

        if publish_config['TtlSec'] != 0:
            try:
                event_pub_term = self.publisher.ed.pop_event(
                    nan_const.SESSION_CB_ON_SESSION_TERMINATED, publish_config['TtlSec'] + 5)
                self.log.info('%s: %s',
                              nan_const.SESSION_CB_ON_SESSION_TERMINATED,
                              event_pub_term['data'])
                asserts.assert_equal(event_pub_term['data'][nan_const.SESSION_CB_KEY_REASON],
                                     nan_const.TERMINATE_REASON_DONE,
                                     "Publisher terminate reason is not DONE")
            except queue.Empty:
                asserts.fail('Timed out while waiting for %s on publisher' %
                             nan_const.SESSION_CB_ON_SESSION_TERMINATED)
        if subscribe_config['TtlSec'] != 0:
            try:
                event_sub_term = self.subscriber.ed.pop_event(
                    nan_const.SESSION_CB_ON_SESSION_TERMINATED, subscribe_config['TtlSec'] + 5)
                self.log.info('%s: %s',
                              nan_const.SESSION_CB_ON_SESSION_TERMINATED,
                              event_sub_term['data'])
                asserts.assert_equal(event_sub_term['data'][nan_const.SESSION_CB_KEY_REASON],
                                     nan_const.TERMINATE_REASON_DONE,
                                     "Subscriber terminate reason is not DONE")
            except queue.Empty:
                asserts.fail('Timed out while waiting for %s on subscriber' %
                             nan_const.SESSION_CB_ON_SESSION_TERMINATED)

    @generated_test
    def test_nan_discovery_session(self):
        """Perform NAN configuration, discovery, and message exchange.

        Test multiple discovery types:
        - Unsolicited publish + passive subscribe
        - Solicited publish + active subscribe
        """

        discovery_configs = ({'Title': 'ActivePub',
                              'PublishConfig': self.publish_config,
                              'SubscribeConfig': self.subscribe_config},
                             {'Title': 'ActiveSub',
                              'PublishConfig': dict(self.publish_config, **{'PublishType': 1}),
                              'SubscribeConfig': dict(self.subscribe_config,
                                                      **{'SubscribeType': 1})},
                             {'Title': 'ActivePub-LimitedTtl',
                              'PublishConfig': dict(self.publish_config, **{"TtlSec": 20}),
                              'SubscribeConfig': dict(self.subscribe_config, **{"TtlSec": 20})})
        name_func = lambda discovery_config : ("test_nan_discovery_session__%s"
                                               ) % discovery_config['Title']
        self.run_generated_testcases(
            self.run_nan_discovery_session,
            discovery_configs,
            name_func = name_func)

    def run_nan_messaging(self, retry_count):
        """Perform NAN configuration, discovery, and large message exchange.

        Args:
            retry_count: retransmission count - from 0 to nan_const.MAX_TX_RETRIES

        Configuration: 2 devices, one acting as Publisher (P) and the
        other as Subscriber (S)

        Logical steps:
          * P & S initiate NAN clustering (if not already up)
          * P & S wait for NAN connection confirmation
          * P starts publishing
          * S starts subscribing
          * S waits for a match (discovery) notification
          * S sends XX messages to P
          * S confirms that all XXX messages were transmitted
          * P confirms that all XXX messages are received
        """
        self.publisher = self.android_devices[0]
        self.subscriber = self.android_devices[1]
        results = {}
        results['num_non_empty_messages'] = 100
        results['num_null_and_empty_messages'] = 10 # one of each in sequence until reach count

        # Start Test
        pub_connect_id = self.exec_connect(self.publisher, "publisher")
        sub_connect_id = self.exec_connect(self.subscriber, "subscriber")

        pub_id = self.publisher.droid.wifiNanPublish(pub_connect_id, self.publish_config)
        sub_id = self.subscriber.droid.wifiNanSubscribe(sub_connect_id, self.subscribe_config)

        try:
            event_sub_match = self.subscriber.ed.pop_event(
                nan_const.SESSION_CB_ON_SERVICE_DISCOVERED, EVENT_TIMEOUT)
            self.log.info('%s: %s', nan_const.SESSION_CB_ON_SERVICE_DISCOVERED,
                          event_sub_match['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on Subscriber' %
                         nan_const.SESSION_CB_ON_SERVICE_DISCOVERED)
        self.log.debug(event_sub_match)

        # send all messages at once
        for i in range(results['num_non_empty_messages']):
            self.msg_id = self.msg_id + 1
            self.subscriber.droid.wifiNanSendMessage(sub_id, event_sub_match['data']['peerId'],
                                                     self.msg_id, "msg %s" % i, retry_count)

        # send all empty & null messages
        for i in range(results['num_null_and_empty_messages']):
            self.msg_id = self.msg_id + 1
            msg_to_send = None if (i % 2) else "" # flip between null and ""
            self.subscriber.droid.wifiNanSendMessage(sub_id, event_sub_match['data']['peerId'],
                                                     self.msg_id, msg_to_send, retry_count)

        # wait for all messages to be transmitted correctly
        results['num_tx_ok'] = 0
        results['num_tx_fail'] = 0
        tx_ok_stats = []
        tx_fail_stats = []
        events_regex = '%s|%s' % (nan_const.SESSION_CB_ON_MESSAGE_SEND_FAILED,
                                  nan_const.SESSION_CB_ON_MESSAGE_SENT)
        while (results['num_tx_ok'] + results['num_tx_fail']) < (
                    results['num_non_empty_messages'] + results['num_null_and_empty_messages']):
            try:
                events = self.subscriber.ed.pop_events(events_regex,
                                                       EVENT_TIMEOUT)

                for event in events:
                    if event['name'] == nan_const.SESSION_CB_ON_MESSAGE_SENT:
                        results['num_tx_ok'] = results['num_tx_ok'] + 1
                        if nan_const.SESSION_CB_KEY_LATENCY_MS in event['data']:
                            tx_ok_stats.append(event['data'][nan_const.SESSION_CB_KEY_LATENCY_MS])
                    if event['name'] == nan_const.SESSION_CB_ON_MESSAGE_SEND_FAILED:
                        results['num_tx_fail'] = results['num_tx_fail'] + 1
                        if nan_const.SESSION_CB_KEY_LATENCY_MS in event['data']:
                            tx_fail_stats.append(event['data'][nan_const.SESSION_CB_KEY_LATENCY_MS])
            except queue.Empty:
                self.log.warning('Timed out while waiting for %s on Subscriber'
                                 ' - %d events received', events_regex,
                                 results['num_tx_ok'] + results['num_tx_fail'])
                break
        self.log.info('Transmission stats: %d success, %d fail', results['num_tx_ok'],
                      results['num_tx_fail'])
        self.extract_stats(tx_ok_stats, results, 'tx_ok_latency', 'Successful tx')
        self.extract_stats(tx_ok_stats, results, 'tx_fail_latency', 'Fail tx')

        # validate that all messages are received (not just the correct
        # number of messages - since on occasion there may be duplicates
        # received).
        results['num_non_empty_received'] = 0
        results['num_unique_received'] = 0
        results['num_empty_received'] = 0
        messages = {}
        while (results['num_unique_received'] != results['num_non_empty_messages']) or (
        results['num_empty_received'] != results['num_null_and_empty_messages']):
            try:
                event = self.publisher.ed.pop_event(
                    nan_const.SESSION_CB_ON_MESSAGE_RECEIVED, EVENT_TIMEOUT)
                msg = event['data']['messageAsString']
                if msg:
                    results['num_non_empty_received'] = results['num_non_empty_received'] + 1
                    if msg not in messages:
                        results['num_unique_received'] = results['num_unique_received'] + 1
                        messages[msg] = 0
                    messages[msg] = messages[msg] + 1
                else:
                    results['num_empty_received'] = results['num_empty_received'] + 1
                self.log.debug('%s: %s',
                               nan_const.SESSION_CB_ON_MESSAGE_RECEIVED, msg)
            except queue.Empty:
                asserts.fail('Timed out while waiting for %s on Publisher: %d non-empty '
                             'messages received, %d unique messages, %d empty messages' % (
                             nan_const.SESSION_CB_ON_MESSAGE_RECEIVED,
                             results['num_non_empty_received'],
                             results['num_unique_received'],
                             results['num_empty_received']), extras=results)
        self.log.info('Reception stats: %d non-empty received (%d unique), %d empty',
                      results['num_non_empty_received'], results['num_unique_received'],
                      results['num_empty_received'])
        if results['num_non_empty_received'] != results['num_unique_received']:
            self.log.info('%d duplicate receptions of %d messages: %s',
                          results['num_non_empty_received'] - results['num_unique_received'],
                          results['num_non_empty_received'], messages)
        if results['num_empty_received'] != results['num_null_and_empty_messages']:
            self.log.info('%d extra empty/null message reception',
                          results['num_empty_received'] - results['num_null_and_empty_messages'])
        asserts.explicit_pass("run_nan_messaging pass finished successfully", extras=results)

    @generated_test
    def test_nan_messaging(self):
        """Perform NAN configuration, discovery, and large message exchange.

        Test multiple message send retry counts.
        """
        name_func = lambda retry_count : "test_nan_messaging__retries_%d" % retry_count
        self.run_generated_testcases(
            self.run_nan_messaging,
            [0, nan_const.MAX_TX_RETRIES],
            name_func = name_func)

    def test_nan_messaging_latency(self):
        """Measure the latency of NAN message transmission which are not queued. Unqueued
        message transmission data is a function of raw protocol and firmware behavior.

        Configuration: 2 devices, one acting as Publisher (P) and the
        other as Subscriber (S)

        Logical steps:
          * P & S initiate NAN clustering (if not already up)
          * P & S wait for NAN connection confirmation
          * P starts publishing
          * S starts subscribing
          * S waits for a match (discovery) notification
          * Loop:
          *    S sends 1 message to P
          *    S confirms that message transmitted and measures latency
        """
        self.publisher = self.android_devices[0]
        self.subscriber = self.android_devices[1]
        results = {}
        results['num_messages'] = 100

        # Start Test
        pub_connect_id = self.exec_connect(self.publisher, "publisher")
        sub_connect_id = self.exec_connect(self.subscriber, "subscriber")

        pub_id = self.publisher.droid.wifiNanPublish(pub_connect_id, self.publish_config)
        sub_id = self.subscriber.droid.wifiNanSubscribe(sub_connect_id, self.subscribe_config)

        try:
            event_sub_match = self.subscriber.ed.pop_event(
                nan_const.SESSION_CB_ON_SERVICE_DISCOVERED, EVENT_TIMEOUT)
            self.log.info('%s: %s', nan_const.SESSION_CB_ON_SERVICE_DISCOVERED,
                          event_sub_match['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on Subscriber' %
                         nan_const.SESSION_CB_ON_SERVICE_DISCOVERED)
        self.log.debug(event_sub_match)

        results['num_tx_ok'] = 0
        results['num_tx_fail'] = 0
        tx_ok_stats = []
        tx_fail_stats = []
        events_regex = '%s|%s' % (nan_const.SESSION_CB_ON_MESSAGE_SEND_FAILED,
                                  nan_const.SESSION_CB_ON_MESSAGE_SENT)
        for i in range(results['num_messages']):
            self.msg_id = self.msg_id + 1
            self.subscriber.droid.wifiNanSendMessage(sub_id, event_sub_match['data']['peerId'],
                                                     self.msg_id, "msg %s" % i, 0)
            try:
                events = self.subscriber.ed.pop_events(events_regex, EVENT_TIMEOUT)
                for event in events:
                    if event['name'] == nan_const.SESSION_CB_ON_MESSAGE_SENT:
                        results['num_tx_ok'] = results['num_tx_ok'] + 1
                        if nan_const.SESSION_CB_KEY_LATENCY_MS in event['data']:
                            tx_ok_stats.append(event['data'][nan_const.SESSION_CB_KEY_LATENCY_MS])
                    if event['name'] == nan_const.SESSION_CB_ON_MESSAGE_SEND_FAILED:
                        results['num_tx_fail'] = results['num_tx_fail'] + 1
                        if nan_const.SESSION_CB_KEY_LATENCY_MS in event['data']:
                            tx_fail_stats.append(event['data'][nan_const.SESSION_CB_KEY_LATENCY_MS])
            except queue.Empty:
                asserts.fail('Timed out while waiting for %s on Subscriber', events_regex,
                             extras=results)
        self.extract_stats(tx_ok_stats, results, 'tx_ok_latency', 'Successful tx')
        self.extract_stats(tx_fail_stats, results, 'tx_fail_latency', 'Fail tx')
        asserts.explicit_pass('test_nan_messaging_no_queue finished successfully', extras=results)

    def test_nan_rtt(self):
        """Perform NAN configuration, discovery, and RTT.

        Configuration: 2 devices, one acting as Publisher (P) and the
        other as Subscriber (S)

        Logical steps:
          * P & S initiate NAN clustering (if not already up)
          * P & S wait for NAN connection confirmation
          * P starts publishing
          * S starts subscribing
          * S waits for a match (discovery) notification
          * S performs 3 RTT measurements with P
        """
        # Configure Test
        self.publisher = self.android_devices[0]
        self.subscriber = self.android_devices[1]
        rtt_iterations = 10

        # Start Test
        pub_connect_id = self.exec_connect(self.publisher, "publisher")
        sub_connect_id = self.exec_connect(self.subscriber, "subscriber")

        pub_id = self.publisher.droid.wifiNanPublish(pub_connect_id, self.publish_config)
        sub_id = self.subscriber.droid.wifiNanSubscribe(sub_connect_id, self.subscribe_config)

        try:
            event_sub_match = self.subscriber.ed.pop_event(
                nan_const.SESSION_CB_ON_SERVICE_DISCOVERED, EVENT_TIMEOUT)
            self.log.info('%s: %s', nan_const.SESSION_CB_ON_SERVICE_DISCOVERED,
                          event_sub_match['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on Subscriber' %
                         nan_const.SESSION_CB_ON_SERVICE_DISCOVERED)
        self.log.debug(event_sub_match)

        self.exec_rtt(device=self.subscriber,
                      session_id=sub_id,
                      peer_id=event_sub_match['data']['peerId'],
                      rtt_param=self.rtt_24_20,
                      label="2.4GHz / 20MHz BW",
                      repeat_count=rtt_iterations)
        self.exec_rtt(device=self.subscriber,
                      session_id=sub_id,
                      peer_id=event_sub_match['data']['peerId'],
                      rtt_param=self.rtt_50_40,
                      label="5Hz / 40MHz BW",
                      repeat_count=rtt_iterations)
        self.exec_rtt(device=self.subscriber,
                      session_id=sub_id,
                      peer_id=event_sub_match['data']['peerId'],
                      rtt_param=self.rtt_50_80,
                      label="5GHz / 80MHz BW",
                      repeat_count=rtt_iterations)


    def test_disable_wifi_during_connection(self):
        """Validate behavior when Wi-Fi is disabled during an active NAN
        connection. Expected behavior: receive an onNanDown(1002) event.

        Configuration: 1 device - the DUT.

        Logical steps:
          * DUT initiate NAN clustering (if not already up)
          * DUT waits for NAN connection confirmation
          * DUT starts publishing
          * Disable Wi-Fi
          * DUT waits for an onNanDown(1002) event and confirms that received
        """
        # Configure Test
        self.dut = self.android_devices[0]

        # Start Test
        connect_id = self.dut.droid.wifiNanAttach()

        try:
            event = self.dut.ed.pop_event(nan_const.EVENT_CB_ON_ATTACHED, EVENT_TIMEOUT)
            self.log.info('%s: %s', nan_const.EVENT_CB_ON_ATTACHED, event['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on dut' % nan_const.EVENT_CB_ON_ATTACHED)
        self.log.debug(event)

        pub_id = self.dut.droid.wifiNanPublish(connect_id, self.publish_config)

        asserts.assert_true(
            wutils.wifi_toggle_state(self.dut, False),
            "Failed disabling Wi-Fi interface on dut")

        try:
            event = self.dut.ed.pop_event(nan_const.BROADCAST_WIFI_NAN_NOT_AVAILABLE,
                                          EVENT_TIMEOUT)
            self.log.info(nan_const.BROADCAST_WIFI_NAN_NOT_AVAILABLE)
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on dut' %
                         nan_const.BROADCAST_WIFI_NAN_NOT_AVAILABLE)
        self.log.debug(event)

    def test_nan_data_path(self):
        """Perform NAN configuration, discovery, data-path setup, and data
        transfer.

        Configuration: 2 devices, one acting as Publisher (P) and the
        other as Subscriber (S)

        Logical steps:
          * P & S initiate NAN clustering (if not already up)
          * P & S wait for NAN connection confirmation
          * P starts publishing
          * S starts subscribing
          * S waits for a match (discovery) notification
          * S sends a message to P
          * P waits for message
          * P creates a NAN network to S as RESPONDER
          * P sends a message to S
          * S waits for message
          * S creates a NAN network to P as INITIATOR (order important!)
          * Both P & S wait for events confirming network set up
          * P registers NSD service
          * S discovers NSD service and obtains P's IP address
          * run iperf3 between P (server) and S (client)
          * unregister network callback on S
        """
        # Configure Test
        self.publisher = self.android_devices[0]
        self.subscriber = self.android_devices[1]
        results = {}

        sub2pub_msg = "Get ready!"
        pub2sub_msg = "Ready!"
        test_token = "Token / <some magic string>"

        # Start Test
        pub_connect_id = self.exec_connect(self.publisher, "publisher")
        sub_connect_id = self.exec_connect(self.subscriber, "subscriber")

        # Discovery: publish + subscribe + wait for match
        pub_id = self.publisher.droid.wifiNanPublish(pub_connect_id, self.publish_config)
        sub_id = self.subscriber.droid.wifiNanSubscribe(sub_connect_id, self.subscribe_config)

        def filter_callbacks(event, key, name):
            return event['data'][key] == name

        try:
            event_sub_match = self.subscriber.ed.pop_event(
                nan_const.SESSION_CB_ON_SERVICE_DISCOVERED, EVENT_TIMEOUT)
            self.log.info('%s: %s', nan_const.SESSION_CB_ON_SERVICE_DISCOVERED,
                          event_sub_match['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on Subscriber' %
                         nan_const.SESSION_CB_ON_SERVICE_DISCOVERED)
        self.log.debug(event_sub_match)

        # S sends message to P
        self.reliable_tx(self.subscriber, sub_id,
                         event_sub_match['data']['peerId'], sub2pub_msg)

        try:
            event_pub_rx = self.publisher.ed.pop_event(
                nan_const.SESSION_CB_ON_MESSAGE_RECEIVED, EVENT_TIMEOUT)
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on publisher' %
                         nan_const.SESSION_CB_ON_MESSAGE_RECEIVED)
        self.log.info('%s: %s', nan_const.SESSION_CB_ON_MESSAGE_RECEIVED,
                      event_pub_rx['data'])
        asserts.assert_equal(event_pub_rx['data']['messageAsString'],
                             sub2pub_msg,
                             "Subscriber -> publisher message corrupted")

        # P requests a NAN network as RESPONDER
        pub_ns = self.publisher.droid.wifiNanCreateNetworkSpecifier(
            nan_const.DATA_PATH_RESPONDER, pub_id,
            event_pub_rx['data']['peerId'], test_token)
        self.log.info("Publisher network specifier - '%s'", pub_ns)
        self.network_req['NetworkSpecifier'] = pub_ns
        pub_req_key = self.publisher.droid.connectivityRequestNetwork(
            self.network_req)

        # P sends message to S
        self.reliable_tx(self.publisher, pub_id, event_pub_rx['data']['peerId'],
                         pub2sub_msg)

        try:
            event_sub_rx = self.subscriber.ed.pop_event(
                nan_const.SESSION_CB_ON_MESSAGE_RECEIVED, EVENT_TIMEOUT)
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s on subscriber' %
                         nan_const.SESSION_CB_ON_MESSAGE_RECEIVED)
        self.log.info('%s: %s', nan_const.SESSION_CB_ON_MESSAGE_RECEIVED,
                      event_sub_rx['data'])
        asserts.assert_equal(event_sub_rx['data']['messageAsString'],
                             pub2sub_msg,
                             "Publisher -> subscriber message corrupted")

        # S requests a NAN network as INITIATOR
        sub_ns = self.subscriber.droid.wifiNanCreateNetworkSpecifier(
            nan_const.DATA_PATH_INITIATOR, sub_id,
            event_sub_rx['data']['peerId'], test_token)
        self.log.info("Subscriber network specifier - '%s'", sub_ns)
        self.network_req['NetworkSpecifier'] = sub_ns
        sub_req_key = self.subscriber.droid.connectivityRequestNetwork(
            self.network_req)

        # Wait until both S and P get confirmation that network formed
        try:
            event_network = self.subscriber.ed.wait_for_event(
                con_const.EVENT_NETWORK_CALLBACK, filter_callbacks,
                EVENT_TIMEOUT,
                key=con_const.NETWORK_CB_KEY_EVENT,
                name=con_const.NETWORK_CB_LINK_PROPERTIES_CHANGED)
            self.log.info('Subscriber %s: %s',
                          con_const.EVENT_NETWORK_CALLBACK,
                          event_network['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s/%s on Subscriber' % (
                con_const.EVENT_NETWORK_CALLBACK,
                con_const.NETWORK_CB_LINK_PROPERTIES_CHANGED))
        self.log.debug(event_network)
        sub_nan_if = event_network['data']['interfaceName']

        try:
            event_network = self.publisher.ed.wait_for_event(
                con_const.EVENT_NETWORK_CALLBACK, filter_callbacks,
                EVENT_TIMEOUT,
                key=con_const.NETWORK_CB_KEY_EVENT,
                name=con_const.NETWORK_CB_LINK_PROPERTIES_CHANGED)
            self.log.info('Publisher %s: %s', con_const.EVENT_NETWORK_CALLBACK,
                          event_network['data'])
        except queue.Empty:
            asserts.fail('Timed out while waiting for %s/%s on Publisher' % (
                con_const.EVENT_NETWORK_CALLBACK,
                con_const.NETWORK_CB_LINK_PROPERTIES_CHANGED))
        self.log.debug(event_network)

        try:
            # P registers NSD service (i.e. starts publishing)
            nsd_reg = self.publisher.droid.nsdRegisterService(
                self.nsd_service_info)
            try:
                event_nsd = self.publisher.ed.wait_for_event(
                    nsd_const.REG_LISTENER_EVENT, filter_callbacks,
                    EVENT_TIMEOUT, key=nsd_const.REG_LISTENER_CALLBACK,
                    name=nsd_const.REG_LISTENER_EVENT_ON_SERVICE_REGISTERED)
                self.log.info('Publisher %s: %s',
                            nsd_const.REG_LISTENER_EVENT_ON_SERVICE_REGISTERED,
                            event_nsd['data'])
            except queue.Empty:
                asserts.fail('Timed out while waiting for %s on Publisher' %
                             nsd_const.REG_LISTENER_EVENT_ON_SERVICE_REGISTERED)

            # S starts NSD discovery
            nsd_discovery = self.subscriber.droid.nsdDiscoverServices(
                self.nsd_service_info[nsd_const.NSD_SERVICE_INFO_SERVICE_TYPE])
            try:
                event_nsd = self.subscriber.ed.wait_for_event(
                    nsd_const.DISCOVERY_LISTENER_EVENT, filter_callbacks,
                    EVENT_TIMEOUT,
                    key=nsd_const.DISCOVERY_LISTENER_DATA_CALLBACK,
                    name=nsd_const.DISCOVERY_LISTENER_EVENT_ON_SERVICE_FOUND)
                self.log.info('Subscriber %s: %s',
                          nsd_const.DISCOVERY_LISTENER_EVENT_ON_SERVICE_FOUND,
                          event_nsd['data'])
            except queue.Empty:
                asserts.fail('Timed out while waiting for %s on Subscriber' %
                         nsd_const.DISCOVERY_LISTENER_EVENT_ON_SERVICE_FOUND)

            # S resolves IP address of P from NSD service discovery
            self.subscriber.droid.nsdResolveService(event_nsd['data'])
            try:
                event_nsd = self.subscriber.ed.wait_for_event(
                    nsd_const.RESOLVE_LISTENER_EVENT, filter_callbacks,
                    EVENT_TIMEOUT,
                    key=nsd_const.RESOLVE_LISTENER_DATA_CALLBACK,
                    name=nsd_const.RESOLVE_LISTENER_EVENT_ON_SERVICE_RESOLVED)
                self.log.info('Subscriber %s: %s',
                          nsd_const.RESOLVE_LISTENER_EVENT_ON_SERVICE_RESOLVED,
                          event_nsd['data'])
            except queue.Empty:
                asserts.fail('Timed out while waiting for %s on Subscriber' %
                         nsd_const.RESOLVE_LISTENER_EVENT_ON_SERVICE_RESOLVED)

            # mDNS returns first character as '/' - strip out to get clean IPv6
            pub_ipv6_from_nsd = event_nsd['data'][
                                    nsd_const.NSD_SERVICE_INFO_HOST][1:]
        finally:
            # Stop NSD
            if nsd_reg is not None:
                self.publisher.droid.nsdUnregisterService(nsd_reg)
            if nsd_discovery is not None:
                self.subscriber.droid.nsdStopServiceDiscovery(nsd_discovery)

        # P starts iPerf server
        result, data = self.publisher.run_iperf_server("-D")
        asserts.assert_true(result, "Can't start iperf3 server")

        # S starts iPerf client
        result, data = self.subscriber.run_iperf_client(
            "%s%%%s" % (pub_ipv6_from_nsd, sub_nan_if), "-6 -J")
        self.log.debug(data)
        asserts.assert_true(result,
                            "Failure starting/running iperf3 in client mode")
        self.log.debug(pprint.pformat(data))
        data_json = json.loads(''.join(data))
        results['tx_rate'] = data_json['end']['sum_sent']['bits_per_second']
        results['rx_rate'] = data_json['end']['sum_received']['bits_per_second']
        self.log.info('iPerf3: Sent = %d bps Received = %d bps', results['tx_rate'],
                      results['rx_rate'])
        asserts.explicit_pass('NAN data-path test passes', extras=results)
