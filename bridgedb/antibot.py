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

"""Functions for dealing with bot requests."""

import re
import logging

# Maps transport types and IP version (e.g., "obfs4v4", "vanillav4", or
# "vanillav6") to bridge lines (e.g., "1.2.3.4:1234 ...".
DECOY_BRIDGES = {}

# Maps HTTP request headers (e.g., "Accept-Language") to regular expressions
# that suggest that the request was issued by a bot (e.g., "[Kk]lingon").
BLACKLISTED_REQUEST_HEADERS = {}


def _loadCSV(filename):
    """Load and return the content of the given CSV file.

    :param str filename: The filename to read.
    :rtype: dict
    :returns: A dictionary mapping keys (first column) to values (second
        column).
    """

    csv = dict()
    try:
        with open(filename) as fh:
            for line in fh.readlines():
                if line.count(",") != 1:
                    logging.warning("Line must have exactly one comma: %s" %
                                    line)
                    continue
                key, value = line.split(",")
                csv[key.strip()] = value.strip()
    except IOError as err:
        logging.warning("I/O error while reading from file %s: %s" %
                        (filename, err))

    return csv


def loadBlacklistedRequestHeaders(filename):
    """Load and globally set a dictionary of blacklisted request headers.

    :param str filename: The filename to read.
    """

    content = _loadCSV(filename)
    blacklisted = dict()
    # Turn dictionary values into compiled regular expressions.
    for header, regexp in content.items():
        try:
            blacklisted[header] = re.compile(regexp)
        except Exception as err:
            logging.warning("Skipping regexp %s because we couldn't compile "
                            "it: %s" % (regexp, err))

    global BLACKLISTED_REQUEST_HEADERS
    BLACKLISTED_REQUEST_HEADERS = blacklisted


def loadDecoyBridges(filename):
    """Load and globally set a dictionary of decoy bridges.

    :param str filename: The filename to read.
    """

    d = _loadCSV(filename)
    # Turn our bridge lines (which are strings) into lists.
    decoyBridges = {ttype: [line] for ttype, line in d.items()}

    global DECOY_BRIDGES
    DECOY_BRIDGES = decoyBridges


def getDecoyBridge(transport, ipVersion):
    """Return a decoy bridge or, if none is available, None.

    :param str transport: The desired transport, e.g., "vanilla" or "obfs4".
    :param int ipVersion: The IP version, which must be either 4 or 6.
    :rtype: list
    :returns: Return a list of bridge lines or, if we don't have any, None.
    """

    if ipVersion not in [4, 6]:
        return None

    logging.info("Returning IPv%d decoy bridge for transport %s." %
                 (ipVersion, transport))
    return DECOY_BRIDGES.get("%sv%d" % (transport, ipVersion), None)


def isRequestFromBot(request):
    """Determine if the given request is coming from a bot.

    :type request: :api:`twisted.web.http.Request`
    :param request: A ``Request`` object, including POST arguments which
        should include two key/value pairs.
    :rtype: bool
    :returns: True if the request is coming from a bot and False otherwise.
    """

    for header, badRegexp in BLACKLISTED_REQUEST_HEADERS.items():
        value = request.getHeader(header)
        if value is None:
            continue

        if badRegexp.search(value) is not None:
            logging.info("Found bot request. Headers: %s" %
                         request.requestHeaders)
            return True

    return False
