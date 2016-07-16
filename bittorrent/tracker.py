import socket
import logging
import os
import struct
import time
from random import randint
from urllib.parse import urlparse

from bcoding import bdecode
import requests

CONNECT = 0
CONNECTION_ID = 0x41727101980

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
        self.connection_id = DEFAULT_CONNTION_ID

    def connect(self):
        if self.scheme == 'udp':
            return _self.connect_via_udp()
        elif self.scheme == 'http':
            return self._connect_via_http()

    def _connect_via_udp(self):
        response = _connect_request()
        action, transition_id, connection_id = struct.unpack('!LLQ', response)
        self.connection_id = connection_id
        response = _annouce_request(transition_id)

    def _announce_request(self, transition_id):
        pass


    def _connect_request(self):
        action = CONNECT
        transition_id = randint(0, 1 << 32 -1)
        message = struct.pack('!QLL', self.connection_id, action, transition_id)
        # self.logger.info(transition_id)
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

        keys = {
            'info_hash': self.torrent.info_hash,
            'peer_id': self.torrent.peer_id,
            'left': self.torrent.left,
            'downloaded': 0,
            'uploaded': 0,
            'port': 6881,
            'compact': 1,
            'event': 'started'
        }

        r = requests.get(self.url, params=keys)
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
