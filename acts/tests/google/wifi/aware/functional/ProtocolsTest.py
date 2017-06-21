#!/usr/bin/python3.4
#
#   Copyright 2017 - The Android Open Source Project
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

from acts import asserts
from acts.test_utils.net import nsd_const as nconsts
from acts.test_utils.wifi.aware import aware_const as aconsts
from acts.test_utils.wifi.aware import aware_test_utils as autils
from acts.test_utils.wifi.aware.AwareBaseTest import AwareBaseTest


class ProtocolsTest(AwareBaseTest):
  """Set of tests for Wi-Fi Aware data-paths: validating protocols running on
  top of a data-path"""

  SERVICE_NAME = "GoogleTestServiceXY"

  def __init__(self, controllers):
    AwareBaseTest.__init__(self, controllers)

  def run_ping6(self, dut, peer_ipv6, dut_if):
    """Run a ping6 over the specified device/link

    Args:
      dut: Device on which to execute ping6
      peer_ipv6: IPv6 address of the peer to ping
      dut_if: interface name on the dut
    """
    cmd = "ping6 -c 3 -W 5 %s%%%s" % (peer_ipv6, dut_if)
    results = dut.adb.shell(cmd)
    self.log.info("cmd='%s' -> '%s'", cmd, results)
    if results == "":
      asserts.fail("ping6 empty results - seems like a failure")

  ########################################################################

  def test_ping6_oob(self):
    """Validate that ping6 works correctly on an NDP created using OOB (out-of
    band) discovery"""
    init_dut = self.android_devices[0]
    resp_dut = self.android_devices[1]

    # create NDP
    (init_req_key, resp_req_key, init_aware_if, resp_aware_if, init_ipv6,
     resp_ipv6) = autils.create_oob_ndp(init_dut, resp_dut)
    self.log.info("Interface names: I=%s, R=%s", init_aware_if, resp_aware_if)
    self.log.info("Interface addresses (IPv6): I=%s, R=%s", init_ipv6,
                  resp_ipv6)

    # run ping6
    self.run_ping6(init_dut, resp_ipv6, init_aware_if)
    self.run_ping6(resp_dut, init_ipv6, resp_aware_if)

    # clean-up
    resp_dut.droid.connectivityUnregisterNetworkCallback(resp_req_key)
    init_dut.droid.connectivityUnregisterNetworkCallback(init_req_key)

  def test_ping6_ib_unsolicited_passive(self):
    """Validate that ping6 works correctly on an NDP created using Aware
    discovery with UNSOLICITED/PASSIVE sessions."""
    p_dut = self.android_devices[0]
    s_dut = self.android_devices[1]

    # create NDP
    (p_req_key, s_req_key, p_aware_if, s_aware_if, p_ipv6,
     s_ipv6) = autils.create_ib_ndp(
         p_dut,
         s_dut,
         p_config=autils.create_discovery_config(
             self.SERVICE_NAME, aconsts.PUBLISH_TYPE_UNSOLICITED),
         s_config=autils.create_discovery_config(
             self.SERVICE_NAME, aconsts.SUBSCRIBE_TYPE_PASSIVE),
         device_startup_offset=self.device_startup_offset)
    self.log.info("Interface names: P=%s, S=%s", p_aware_if, s_aware_if)
    self.log.info("Interface addresses (IPv6): P=%s, S=%s", p_ipv6, s_ipv6)

    # run ping6
    self.run_ping6(p_dut, s_ipv6, p_aware_if)
    self.run_ping6(s_dut, p_ipv6, s_aware_if)

    # clean-up
    p_dut.droid.connectivityUnregisterNetworkCallback(p_req_key)
    s_dut.droid.connectivityUnregisterNetworkCallback(s_req_key)

  def test_ping6_ib_solicited_active(self):
    """Validate that ping6 works correctly on an NDP created using Aware
    discovery with SOLICITED/ACTIVE sessions."""
    p_dut = self.android_devices[0]
    s_dut = self.android_devices[1]

    # create NDP
    (p_req_key, s_req_key, p_aware_if, s_aware_if, p_ipv6,
     s_ipv6) = autils.create_ib_ndp(
         p_dut,
         s_dut,
         p_config=autils.create_discovery_config(
             self.SERVICE_NAME, aconsts.PUBLISH_TYPE_SOLICITED),
         s_config=autils.create_discovery_config(self.SERVICE_NAME,
                                                 aconsts.SUBSCRIBE_TYPE_ACTIVE),
         device_startup_offset=self.device_startup_offset)
    self.log.info("Interface names: P=%s, S=%s", p_aware_if, s_aware_if)
    self.log.info("Interface addresses (IPv6): P=%s, S=%s", p_ipv6, s_ipv6)

    # run ping6
    self.run_ping6(p_dut, s_ipv6, p_aware_if)
    self.run_ping6(s_dut, p_ipv6, s_aware_if)

    # clean-up
    p_dut.droid.connectivityUnregisterNetworkCallback(p_req_key)
    s_dut.droid.connectivityUnregisterNetworkCallback(s_req_key)

  def test_nsd_oob(self):
    """Validate that NSD (mDNS) works correctly on an NDP created using OOB
    (out-of band) discovery"""
    init_dut = self.android_devices[0]
    resp_dut = self.android_devices[1]

    # create NDP
    (init_req_key, resp_req_key, init_aware_if, resp_aware_if, init_ipv6,
     resp_ipv6) = autils.create_oob_ndp(init_dut, resp_dut)
    self.log.info("Interface names: I=%s, R=%s", init_aware_if, resp_aware_if)
    self.log.info("Interface addresses (IPv6): I=%s, R=%s", init_ipv6,
                  resp_ipv6)

    # run NSD
    nsd_service_info = {
        "serviceInfoServiceName": "sl4aTestAwareNsd",
        "serviceInfoServiceType": "_simple-tx-rx._tcp.",
        "serviceInfoPort": 2257
    }
    nsd_reg = None
    nsd_discovery = None
    try:
      # Initiator registers an NSD service
      nsd_reg = init_dut.droid.nsdRegisterService(nsd_service_info)
      event_nsd = autils.wait_for_event_with_keys(
          init_dut, nconsts.REG_LISTENER_EVENT, autils.EVENT_TIMEOUT,
          (nconsts.REG_LISTENER_CALLBACK,
           nconsts.REG_LISTENER_EVENT_ON_SERVICE_REGISTERED))
      self.log.info("Initiator %s: %s",
                    nconsts.REG_LISTENER_EVENT_ON_SERVICE_REGISTERED,
                    event_nsd["data"])

      # Responder starts an NSD discovery
      nsd_discovery = resp_dut.droid.nsdDiscoverServices(
          nsd_service_info[nconsts.NSD_SERVICE_INFO_SERVICE_TYPE])
      event_nsd = autils.wait_for_event_with_keys(
          resp_dut, nconsts.DISCOVERY_LISTENER_EVENT, autils.EVENT_TIMEOUT,
          (nconsts.DISCOVERY_LISTENER_DATA_CALLBACK,
           nconsts.DISCOVERY_LISTENER_EVENT_ON_SERVICE_FOUND))
      self.log.info("Responder %s: %s",
                    nconsts.DISCOVERY_LISTENER_EVENT_ON_SERVICE_FOUND,
                    event_nsd["data"])

      # Responder resolves IP address of Initiator from NSD service discovery
      resp_dut.droid.nsdResolveService(event_nsd["data"])
      event_nsd = autils.wait_for_event_with_keys(
          resp_dut, nconsts.RESOLVE_LISTENER_EVENT, autils.EVENT_TIMEOUT,
          (nconsts.RESOLVE_LISTENER_DATA_CALLBACK,
           nconsts.RESOLVE_LISTENER_EVENT_ON_SERVICE_RESOLVED))
      self.log.info("Responder %s: %s",
                    nconsts.RESOLVE_LISTENER_EVENT_ON_SERVICE_RESOLVED,
                    event_nsd["data"])

      # mDNS returns first character as '/' - strip
      # out to get clean IPv6
      init_ipv6_nsd = event_nsd["data"][nconsts.NSD_SERVICE_INFO_HOST][1:]

      asserts.assert_equal(
          init_ipv6, init_ipv6_nsd,
          "Initiator's IPv6 address obtained through NSD doesn't match!?")
    finally:
      # Stop NSD
      if nsd_reg is not None:
        init_dut.droid.nsdUnregisterService(nsd_reg)
      if nsd_discovery is not None:
        resp_dut.droid.nsdStopServiceDiscovery(nsd_discovery)

    # clean-up
    resp_dut.droid.connectivityUnregisterNetworkCallback(resp_req_key)
    init_dut.droid.connectivityUnregisterNetworkCallback(init_req_key)
