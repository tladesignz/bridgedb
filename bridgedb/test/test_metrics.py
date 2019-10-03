# -*- coding: utf-8 ; test-case-name: bridgedb.test.test_metrics ; -*-
# _____________________________________________________________________________
#
# This file is part of BridgeDB, a Tor bridge distribution system.
#
# :authors: please see included AUTHORS file
# :copyright: (c) 2019, The Tor Project, Inc.
#             (c) 2019, Philipp Winter
# :license: see LICENSE for licensing information
# _____________________________________________________________________________

"""Unittests for the :mod:`bridgedb.metrics` module.

These tests are meant to ensure that the :mod:`bridgedb.metrics` module is
functioning as expected.
"""

import StringIO
import json
import os

from bridgedb import metrics
from bridgedb.test.https_helpers import DummyRequest
from bridgedb.distributors.email.server import SMTPMessage
from bridgedb.test.email_helpers import _createMailServerContext
from bridgedb.test.email_helpers import _createConfig
from bridgedb.distributors.moat import server

from twisted.trial import unittest
from twisted.test import proto_helpers


class StateTest(unittest.TestCase):

    def setUp(self):
        self.topDir = os.getcwd().rstrip('_trial_temp')
        self.captchaDir = os.path.join(self.topDir, 'captchas')

        # Clear all singletons before each test to prevent cross-test
        # interference.
        type(metrics.HTTPSMetrics()).clear()
        type(metrics.EmailMetrics()).clear()
        type(metrics.MoatMetrics()).clear()

        metrics.setSupportedTransports({
            'obfs2': False,
            'obfs3': True,
            'obfs4': True,
            'scramblesuit': True,
            'fte': True,
        })

        self.metrix = metrics.HTTPSMetrics()
        self.key = self.metrix.createKey("https", "obfs4", "de", True, None)

    def test_binning(self):

        key = self.metrix.createKey("https", "obfs4", "de", True, None)
        self.metrix.coldMetrics = self.metrix.hotMetrics

        # A value of 1 should be rounded up to 10.
        self.metrix.inc(key)
        metrixLines = self.metrix.getMetrics()
        key, value = metrixLines[0].split(" ")
        self.assertTrue(int(value) == 10)

        # A value of 10 should remain 10.
        self.metrix.set(key, 10)
        metrixLines = self.metrix.getMetrics()
        key, value = metrixLines[0].split(" ")
        self.assertTrue(int(value) == 10)

        # A value of 11 should be rounded up to 20.
        self.metrix.inc(key)
        metrixLines = self.metrix.getMetrics()
        key, value = metrixLines[0].split(" ")
        self.assertTrue(int(value) == 20)

    def test_key_manipulation(self):

        self.metrix = metrics.HTTPSMetrics()
        key = self.metrix.createKey("email", "obfs4", "de", True, "none")
        self.assertTrue(key == "email.obfs4.de.success.none")

        self.metrix.inc(key)
        self.assertEqual(self.metrix.hotMetrics[key], 1)

        self.metrix.set(key, 10)
        self.assertEqual(self.metrix.hotMetrics[key], 10)

    def test_rotation(self):

        key = self.metrix.createKey("moat", "obfs4", "de", True, "none")
        self.metrix.inc(key)
        oldHotMetrics = self.metrix.hotMetrics
        self.metrix.rotate()

        self.assertEqual(len(self.metrix.coldMetrics), 1)
        self.assertEqual(len(self.metrix.hotMetrics), 0)
        self.assertEqual(self.metrix.coldMetrics, oldHotMetrics)

    def test_export(self):

        self.metrix.inc(self.key)

        self.metrix.coldMetrics = self.metrix.hotMetrics
        pseudo_fh = StringIO.StringIO()
        metrics.export(pseudo_fh, 0)

        self.assertTrue(len(pseudo_fh.getvalue()) > 0)

        lines = pseudo_fh.getvalue().split("\n")
        self.assertTrue(lines[0].startswith("bridgedb-metrics-end"))
        self.assertTrue(lines[1].startswith("bridgedb-metrics-version"))
        self.assertTrue(lines[2] ==
                        "bridgedb-metric-count https.obfs4.de.success.None 10")

    def test_https_metrics(self):

        origFunc = metrics.resolveCountryCode
        metrics.resolveCountryCode = lambda _: "US"

        key1 = "https.obfs4.us.success.none"
        req1 = DummyRequest([b"bridges?transport=obfs4"])
        # We have to set the request args manually when using a DummyRequest.
        req1.args.update({'transport': ['obfs4']})
        req1.getClientIP = lambda: "3.3.3.3"

        self.metrix.recordValidHTTPSRequest(req1)
        self.assertTrue(self.metrix.hotMetrics[key1] == 1)

        key2 = "https.obfs4.us.fail.none"
        req2 = DummyRequest([b"bridges?transport=obfs4"])
        # We have to set the request args manually when using a DummyRequest.
        req2.args.update({'transport': ['obfs4']})
        req2.getClientIP = lambda: "3.3.3.3"
        self.metrix.recordInvalidHTTPSRequest(req2)
        self.assertTrue(self.metrix.hotMetrics[key2] == 1)

        metrics.resolveCountryCode = origFunc

    def test_email_metrics(self):

        config = _createConfig()
        context = _createMailServerContext(config)
        message = SMTPMessage(context)
        message.lines = [
            "From: foo@gmail.com",
            "To: bridges@torproject.org",
            "Subject: testing",
            "",
            "get transport obfs4",
        ]

        message.message = message.getIncomingMessage()
        responder = message.responder
        tr = proto_helpers.StringTransportWithDisconnection()
        tr.protocol = responder
        responder.makeConnection(tr)

        email_metrix = metrics.EmailMetrics()

        key1 = "email.obfs4.gmail.success.none"
        email_metrix.recordValidEmailRequest(responder)
        self.assertTrue(email_metrix.hotMetrics[key1] == 1)

        key2 = "email.obfs4.gmail.fail.none"
        email_metrix.recordInvalidEmailRequest(responder)
        self.assertTrue(email_metrix.hotMetrics[key2] == 1)

    def test_moat_metrics(self):

        def create_moat_request():
            encoded_data = json.dumps({
                'data': [{
                    'id': '2',
                    'type': 'moat-solution',
                    'version': server.MOAT_API_VERSION,
                    'transport': 'obfs4',
                    'solution': 'Tvx74PMy',
                    'qrcode': False,
                }]
            })

            request = DummyRequest(["fetch"])
            request.requestHeaders.addRawHeader('Content-Type',
                                                'application/vnd.api+json')
            request.requestHeaders.addRawHeader('Accept',
                                                'application/vnd.api+json')
            request.requestHeaders.addRawHeader('X-Forwarded-For', '3.3.3.3')
            request.headers['X-Forwarded-For'.lower()] = '3.3.3.3'
            request.method = b'POST'
            request.writeContent(encoded_data)

            return request

        metrix = metrics.MoatMetrics()
        metrix.recordValidMoatRequest(create_moat_request())
        metrix.recordInvalidMoatRequest(create_moat_request())

        key1 = "moat.obfs4.us.success.none"
        key2 = "moat.obfs4.us.fail.none"
        self.assertTrue(metrix.hotMetrics[key1] == 1)
        self.assertTrue(metrix.hotMetrics[key2] == 1)
