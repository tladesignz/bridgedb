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

"""Tests for :mod:`bridgedb.antibot`."""

import os
import tempfile

from twisted.trial import unittest
from twisted.web.test.requesthelper import DummyRequest

from bridgedb import antibot


class AntiBot(unittest.TestCase):
    """Unittests for :mod:`bridgedb.antibot`."""

    def write_file(self, content):
        """
        Write the given content to a temporary file.

        We're responsible for deleting the file once we're done.
        """
        fd, filename = tempfile.mkstemp(prefix="bridgedb")
        fh = os.fdopen(fd, "w")
        fh.write(content)
        fh.close()
        return filename

    def test_load_csv(self):
        """Load a valid CSV file."""
        content = "foo,bar\nbar,foo\n"
        filename = self.write_file(content)

        csv = antibot._loadCSV(filename)
        self.assertEqual(csv["foo"], "bar")
        self.assertEqual(csv["bar"], "foo")

        os.unlink(filename)

    def test_load_invalid_csv(self):
        """Load an invalid CSV file that has two commas in one line."""
        content = "foo,bar,bad\nbar,foo\n"
        filename = self.write_file(content)

        csv = antibot._loadCSV(filename)
        self.assertEqual(len(csv), 1)

        os.unlink(filename)

    def test_load_blacklisted_headers(self):
        """Load valid blacklisted request headers."""
        content = "accept-language,[Kk]lingon"
        filename = self.write_file(content)

        antibot.loadBlacklistedRequestHeaders(filename)

        request = DummyRequest([''])
        verdict = antibot.isRequestFromBot(request)
        self.assertFalse(verdict)

        request.requestHeaders.setRawHeaders("accept-language",
                                             ["i speak kllingon"])
        antibot.loadBlacklistedRequestHeaders(filename)
        verdict = antibot.isRequestFromBot(request)
        self.assertFalse(verdict)

        request.requestHeaders.setRawHeaders("accept-language",
                                             ["i speak klingon"])
        antibot.loadBlacklistedRequestHeaders(filename)
        verdict = antibot.isRequestFromBot(request)
        self.assertTrue(verdict)

        os.unlink(filename)

    def test_load_invalid_blacklisted_headers(self):
        """Load invalid blacklisted request headers with a broken regexp."""
        content = "accept-language,[Klingon\nuser-agent,foo*"
        filename = self.write_file(content)

        antibot.loadBlacklistedRequestHeaders(filename)
        self.assertEqual(len(antibot.BLACKLISTED_REQUEST_HEADERS), 1)

        os.unlink(filename)

    def test_load_decoy_bridges(self):
        """Load decoy bridges."""
        obfs4_line = "obfs4 1.2.3.4:1234 FINGERPRINT FOO BAR"
        vanilla_line = "1.2.3.4:1234 FINGERPRINT"

        content = "vanillav4,%s\nobfs4v4,%s" % (vanilla_line, obfs4_line)
        filename = self.write_file(content)

        antibot.loadDecoyBridges(filename)
        self.assertEqual(antibot.getDecoyBridge("obfs4", 4), [obfs4_line])
        self.assertEqual(antibot.getDecoyBridge("vanilla", 4), [vanilla_line])
        self.assertEqual(antibot.getDecoyBridge("vanilla", 6), None)
        self.assertEqual(antibot.getDecoyBridge("vanilla", 7), None)

        os.unlink(filename)
