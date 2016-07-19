import socket
import logging
import os
import struct
import time
from random import randint
from urllib.parse import urlparse, urlencode

from bcoding import bdecode
import requests

CONNECT = 0
ANNOUNCE = 1
DEFAULT_CONNECTION_ID = 0x41727101980

class Tracker():

    def __init__(self, torrent):
        self.logger = logging.getLogger('main.tracker')
        self.torrent = torrent
        self.url = self.torrent.announce_url
        u = urlparse(self.url)
        self.scheme = u.scheme
        self.hostname = u.hostname
        self.port = u.port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.timeout = 2
        self.connection_id = DEFAULT_CONNECTION_ID

    def connect(self):
        if self.scheme == 'udp':
            return self._connect_via_udp()
        elif self.scheme == 'http':
            return self._connect_via_http()

    def _connect_via_udp(self):
        connect_response = self._connect_request()
        action, transition_id, connection_id = struct.unpack('!LLQ', connect_response)
        self.logger.info(transition_id)
        self.connection_id = connection_id
        self.transition_id = transition_id
        if action == CONNECT:
            announce_response = self._announce_request(transition_id)
            self.logger.info(len(announce_response))
            action, transition_id, interval = struct.unpack('!3I', announce_response[:12])
            if transition_id == self.transition_id:
                bin_peers = announce_response[20:]
                return self._decode_peers(bin_peers)
        else:
            self.logger.error('Error sending request to tracker via udp')

    def _announce_request(self, transition_id):
        message = b''.join([
            struct.pack('!Q', self.connection_id),
            struct.pack('!I',  ANNOUNCE),
            struct.pack('!I', transition_id),
            struct.pack('!20s', self.torrent.info_hash),
            struct.pack('!20s', str.encode(self.torrent.peer_id)),
            struct.pack('!Q', 0),
            struct.pack('!Q', self.torrent.left),
            struct.pack('!Q', 0),
            struct.pack('!I', 2),
            struct.pack('!I', 0),
            struct.pack('!i', -1),
            struct.pack('!I', randint(0, 2**32 -1)),
            struct.pack('!H', 6881)
        ])
        return self._send_message(message)


    def _connect_request(self):
        action = CONNECT
        transition_id = randint(0, 2**32 -1)
        message = struct.pack('!QLL', self.connection_id, action, transition_id)
        # self.logger.info(transition_id)
        return self._send_message(message)

    def _send_message(self, message):
        self.sock.sendto(message, (self.hostname, self.port))
        self.sock.settimeout(self.timeout)
        try:
            response = self.sock.recv(1024)
        except socket.timeout:
            self.logger.error('socket timeout')

        return response

    def _connect_via_http(self):
        """
        https://wiki.theory.org/BitTorrentSpecification#Tracker_Request_Parameters
        make a request to tracker which is an HTTP(S) service
        that holds information about the torrent and peers.
        """

        params = {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.torrent.peer_id,
            'left': self.torrent.left,
            'downloaded': 0,
            'uploaded': 0,
            'port': 6881,
            'compact': 1,
            'event': 'started'
        }

        r = requests.get(self.url, params=params)
        response = bdecode(r.content)
        if 'failure reason' not in response:
            return self._decode_peers(response['peers'])
        else:
            time.sleep(response['interval'])

    def _decode_peers(self, bin_peers):
        """
        The first 4 bytes contain the 32-bit ipv4 address.
        The remaining two bytes contain the port number.
        Both address and port use network-byte order.
        """
        offset = 0
        peers = []
        # Length of bin_peers should be multiple of 6
        while offset != len(bin_peers):
            bin_ip = struct.unpack_from('!i', bin_peers, offset)[0]
            hostname = socket.inet_ntoa(struct.pack('!i', bin_ip))
            offset += 4
            port = struct.unpack_from('!H', bin_peers, offset)[0]
            offset += 2
            # peer = Peer(hostname, port, self.torrent)
            # peer = {'hostname': hostname, 'port': port}
            peers.append({'hostname': hostname, 'port': port})

        return peers
