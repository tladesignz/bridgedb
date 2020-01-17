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

"""API for keeping track of BridgeDB metrics, e.g., the demand for bridges
over time.
"""

import logging
import ipaddr
import operator
import json
import datetime

from bridgedb import geo
from bridgedb.distributors.common.http import getClientIP
from bridgedb.distributors.email import request
from bridgedb.distributors.email.distributor import EmailRequestedHelp

from twisted.mail.smtp import Address

# Our data structure to keep track of exit relays.  The variable is of type
# bridgedb.proxy.ProxySet.  We reserve a special country code (determined by
# PROXY_CC below) for exit relays and other proxies.
PROXIES = None

# Our custom country code for IP addresses that we couldn't map to a country.
# This can happen for private IP addresses or if our geo-location provider has
# no mapping.
UNKNOWN_CC = "??"

# Our custom country code for IP addresses that are proxies, e.g., Tor exit
# relays.  The code "zz" is free for assignment for user needs as specified
# here: <https://en.wikipedia.org/w/index.php?title=ISO_3166-1_alpha-2&oldid=906611218#Decoding_table>
PROXY_CC = "ZZ"

# We use BIN_SIZE to reduce the granularity of our counters.  We round up
# numbers to the next multiple of BIN_SIZE, e.g., 28 is rounded up to:
# 10 * 3 = 30.
BIN_SIZE = 10

# The prefix length that we use to keep track of the number of unique subnets
# we have seen HTTPS requests from.
SUBNET_CTR_PREFIX_LEN = 20

# All of the pluggable transports BridgeDB currently supports.
SUPPORTED_TRANSPORTS = None

# Version number for our metrics format.  We increment the version if our
# format changes.
METRICS_VERSION = 1


def setProxies(proxies):
    """Set the given proxies.

    :type proxies: :class:`~bridgedb.proxy.ProxySet`
    :param proxies: The container for the IP addresses of any currently
        known open proxies.
    """
    logging.debug("Setting %d proxies." % len(proxies))
    global PROXIES
    PROXIES = proxies


def setSupportedTransports(supportedTransports):
    """Set the given supported transports.

    :param dict supportedTransports: The transport types that BridgeDB
        currently supports.
    """

    logging.debug("Setting %d supported transports." %
                  len(supportedTransports))
    global SUPPORTED_TRANSPORTS
    SUPPORTED_TRANSPORTS = supportedTransports


def isBridgeTypeSupported(bridgeType):
    """Return `True' or `False' depending on if the given bridge type is
    supported.

    :param str bridgeType: The bridge type, e.g., "vanilla" or "obfs4".
    """

    if SUPPORTED_TRANSPORTS is None:
        logging.error("Bug: Variable SUPPORTED_TRANSPORTS is None.")
        return False

    # Note that "vanilla" isn't a transport protocol (in fact, it's the absence
    # of a transport), which is why it isn't in SUPPORTED_TRANSPORTS.
    return (bridgeType in SUPPORTED_TRANSPORTS) or (bridgeType == "vanilla")


def export(fh, measurementInterval):
    """Export metrics by writing them to the given file handle.

    :param file fh: The file handle to which we're writing our metrics.
    :param int measurementInterval: The number of seconds after which we rotate
        and dump our metrics.
    """

    httpsMetrix = HTTPSMetrics()
    emailMetrix = EmailMetrics()
    moatMetrix = MoatMetrics()

    # Rotate our metrics.
    httpsMetrix.rotate()
    emailMetrix.rotate()
    moatMetrix.rotate()

    numProxies = len(PROXIES) if PROXIES is not None else 0
    if numProxies == 0:
        logging.error("Metrics module doesn't have any proxies.")
    else:
        logging.debug("Metrics module knows about %d proxies." % numProxies)

    now = datetime.datetime.utcnow()
    fh.write("bridgedb-metrics-end %s (%d s)\n" % (
             now.strftime("%Y-%m-%d %H:%M:%S"),
             measurementInterval))
    fh.write("bridgedb-metrics-version %d\n" % METRICS_VERSION)

    httpsLines = httpsMetrix.getMetrics()
    for line in httpsLines:
        fh.write("bridgedb-metric-count %s\n" % line)

    moatLines = moatMetrix.getMetrics()
    for line in moatLines:
        fh.write("bridgedb-metric-count %s\n" % line)

    emailLines = emailMetrix.getMetrics()
    for line in emailLines:
        fh.write("bridgedb-metric-count %s\n" % line)


def resolveCountryCode(ipAddr):
    """Return the country code of the given IP address.

    :param str ipAddr: The IP address to resolve.

    :rtype: str
    :returns: A two-letter country code.
    """

    if ipAddr is None:
        logging.warning("Given IP address was None.  Using %s as country "
                        "code." % UNKNOWN_CC)
        return UNKNOWN_CC

    if PROXIES is None:
        logging.warning("Proxies are not yet set.")
    elif ipAddr in PROXIES:
        return PROXY_CC

    countryCode = geo.getCountryCode(ipaddr.IPAddress(ipAddr))

    # countryCode may be None if GeoIP is unable to map an IP address to a
    # country.
    return UNKNOWN_CC if countryCode is None else countryCode


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args,
                                                                 **kwargs)
        return cls._instances[cls]

    def clear(cls):
        """Drop the instance (necessary for unit tests)."""
        try:
            del cls._instances[cls]
        except KeyError:
            pass


class Metrics(metaclass=Singleton):
    """Base class representing metrics.

    This class provides functionality that our three distribution mechanisms
    share.
    """

    def __init__(self, binSize=BIN_SIZE):
        logging.debug("Instantiating metrics class.")
        self.binSize = binSize

        # Metrics cover a 24 hour period.  To that end, we're maintaining two
        # data structures: our "hot" metrics are currently being populated
        # while our "cold" metrics are finished, and valid for 24 hours.  After
        # that, our hot metrics turn into cold metrics, and we start over.
        self.hotMetrics = dict()
        self.coldMetrics = dict()

    def rotate(self):
        """Rotate our metrics."""

        self.coldMetrics = self.hotMetrics
        self.hotMetrics = dict()

    def findAnomaly(self, request):
        anomaly = "none"

        # TODO: Inspect email for traces of bots, Sherlock Homes-style!
        # See <https://bugs.torproject.org/9316#comment:19> for the rationale.
        # All classes that inherit from Metrics() should implement this method.

        return anomaly

    def getMetrics(self):
        """Get our sanitized current metrics, one per line.

        Metrics are of the form:

            [
             "moat.obfs4.us.success.none 10",
             "https.vanilla.de.success.none 30",
             ...
            ]

        :rtype: list
        :returns: A list of metric lines.
        """
        lines = []
        for key, value in self.coldMetrics.items():
            # Round up our value to the nearest multiple of self.binSize to
            # reduce the accuracy of our real values.
            if (value % self.binSize) > 0:
                value += self.binSize - (value % self.binSize)
            lines.append("%s %d" % (key, value))
        return lines

    def set(self, key, value):
        """Set the given key to the given value.

        :param str key: The time series key.
        :param int value: The time series value.
        """
        self.hotMetrics[key] = value

    def inc(self, key):
        """Increment the given key.

        :param str key: The time series key.
        """
        if key in self.hotMetrics:
            self.hotMetrics[key] += 1
        else:
            self.set(key, 1)

    def createKey(self, distMechanism, bridgeType, countryOrProvider,
                  success, anomaly):
        """Create and return a time series key.

        :param str distMechanism: A string representing our distribution
            mechanism, e.g., "https".
        :param str bridgeType: A string representing the requested bridge
            type, e.g., "vanilla" or "obfs4".
        :param str countryOrProvider: A string representing the client's
            two-letter country code or email provider, e.g., "it" or
            "yahoo.com".
        :param bool success: ``True`` if the request was successful and
            BridgeDB handed out a bridge; ``False`` otherwise.
        :param str anomaly: ``None`` if the request was not anomalous and hence
            believed to have come from a real user; otherwise a string
            representing the type of anomaly.
        :rtype: str
        :returns: A key that uniquely identifies the given metrics
            combinations.
        """

        countryOrProvider = countryOrProvider.lower()
        bridgeType = bridgeType.lower()
        success = "success" if success else "fail"

        key = "%s.%s.%s.%s.%s" % (distMechanism, bridgeType,
                                  countryOrProvider, success, anomaly)

        return key


class HTTPSMetrics(Metrics):

    def __init__(self):
        super(HTTPSMetrics, self).__init__()

        # Maps subnets (e.g., "1.2.0.0/16") to the number of times we've seen
        # requests from the given subnet.
        self.subnetCounter = dict()
        self.keyPrefix = "https"

    def getTopNSubnets(self, n=10):

        sortedByNum = sorted(self.subnetCounter.items(),
                             key=operator.itemgetter(1),
                             reverse=True)
        return sortedByNum[:n]

    def _recordHTTPSRequest(self, request, success):

        logging.debug("HTTPS request has user agent: %s" %
                      request.requestHeaders.getRawHeaders("User-Agent"))

        # Pull the client's IP address out of the request and convert it to a
        # two-letter country code.
        ipAddr = getClientIP(request,
                             useForwardedHeader=True,
                             skipLoopback=False)
        self.updateSubnetCounter(ipAddr)
        countryCode = resolveCountryCode(ipAddr)

        transports = request.args.get("transport", list())
        if len(transports) > 1:
            logging.warning("Expected a maximum of one transport but %d are "
                            "given." % len(transports))

        if len(transports) == 0:
            bridgeType = "vanilla"
        elif transports[0] == "" or transports[0] == "0":
            bridgeType = "vanilla"
        else:
            bridgeType = transports[0]

        # BridgeDB's HTTPS interface exposes transport types as a drop down
        # menu but users can still request anything by manipulating HTTP
        # parameters.
        if not isBridgeTypeSupported(bridgeType):
            logging.warning("User requested unsupported transport type %s "
                            "over HTTPS." % bridgeType)
            return

        logging.debug("Recording %svalid HTTPS request for %s from %s (%s)." %
                      ("" if success else "in",
                       bridgeType, ipAddr, countryCode))

        # Now update our metrics.
        key = self.createKey(self.keyPrefix, bridgeType, countryCode,
                             success, self.findAnomaly(request))
        self.inc(key)

    def recordValidHTTPSRequest(self, request):
        self._recordHTTPSRequest(request, True)

    def recordInvalidHTTPSRequest(self, request):
        self._recordHTTPSRequest(request, False)

    def updateSubnetCounter(self, ipAddr):

        if ipAddr is None:
            return

        nw = ipaddr.IPNetwork(ipAddr + "/" + str(SUBNET_CTR_PREFIX_LEN),
                              strict=False)
        subnet = nw.network.compressed
        logging.debug("Updating subnet counter with %s" % subnet)

        num = self.subnetCounter.get(subnet, 0)
        self.subnetCounter[subnet] = num + 1


class EmailMetrics(Metrics):

    def __init__(self):
        super(EmailMetrics, self).__init__()
        self.keyPrefix = "email"

    def _recordEmailRequest(self, smtpAutoresp, success):

        emailAddrs = smtpAutoresp.getMailTo()
        if len(emailAddrs) == 0:
            # This is just for unit tests.
            emailAddr = Address("foo@gmail.com")
        else:
            emailAddr = emailAddrs[0]

        # Get the requested transport protocol.
        try:
            br = request.determineBridgeRequestOptions(
                    smtpAutoresp.incoming.lines)
        except EmailRequestedHelp:
            return
        bridgeType = "vanilla" if not len(br.transports) else br.transports[0]

        # Over email, transports are requested by typing them.  Typos happen
        # and users can request anything, really.
        if not isBridgeTypeSupported(bridgeType):
            logging.warning("User requested unsupported transport type %s "
                            "over email." % bridgeType)
            return

        logging.debug("Recording %svalid email request for %s from %s." %
                      ("" if success else "in", bridgeType, emailAddr))
        sld = emailAddr.domain.split(".")[0]

        # Now update our metrics.
        key = self.createKey(self.keyPrefix, bridgeType, sld, success,
                             self.findAnomaly(request))
        self.inc(key)

    def recordValidEmailRequest(self, smtpAutoresp):
        self._recordEmailRequest(smtpAutoresp, True)

    def recordInvalidEmailRequest(self, smtpAutoresp):
        self._recordEmailRequest(smtpAutoresp, False)


class MoatMetrics(Metrics):

    def __init__(self):
        super(MoatMetrics, self).__init__()
        self.keyPrefix = "moat"

    def _recordMoatRequest(self, request, success):

        logging.debug("Moat request has user agent: %s" %
                      request.requestHeaders.getRawHeaders("User-Agent"))

        ipAddr = getClientIP(request,
                             useForwardedHeader=True,
                             skipLoopback=False)
        countryCode = resolveCountryCode(ipAddr)

        try:
            encodedClientData = request.content.read()
            clientData = json.loads(encodedClientData)["data"][0]
            transport = clientData["transport"]
            bridgeType = "vanilla" if not len(transport) else transport
        except Exception as err:
            logging.warning("Could not decode request: %s" % err)
            return

        if not isBridgeTypeSupported(bridgeType):
            logging.warning("User requested unsupported transport type %s "
                            "over moat." % bridgeType)
            return

        logging.debug("Recording %svalid moat request for %s from %s (%s)." %
                      ("" if success else "in",
                       bridgeType, ipAddr, countryCode))

        # Now update our metrics.
        key = self.createKey(self.keyPrefix, bridgeType,
                             countryCode, success, self.findAnomaly(request))
        self.inc(key)

    def recordValidMoatRequest(self, request):
        self._recordMoatRequest(request, True)

    def recordInvalidMoatRequest(self, request):
        self._recordMoatRequest(request, False)
