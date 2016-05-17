import struct
import socket
import requests
from bcoding import bdecode
from torrent import Torrent


class TorrentClient():

    def __init__(self, torrent_file):
        self.metainfo = self.read_torrent_file(torrent_file)
        self.torrent = Torrent(self.metainfo)

    def read_torrent_file(self, torrent_file):
        with open(torrent_file, 'rb') as f:
            return bdecode(f.read())


    def connect_to_tracker(self):
        """
        make a request to tracker, which is an HTTP(S) service
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

        r = requests.get(self.torrent.tracker_url, params=keys)
        response = bdecode(r.content)
        return response

    def get_peers(self, tracker_response):
        """
        get peers connected to the torrent.
        peers from the tracker response is bencoded raw binary data,
        this method parses the raw binary data and returns a list of peers
        """
        binary_peers = tracker_response['peers']
        peers = []
        # The first 4 bytes contain the 32-bit ipv4 address.
        # The remaining two bytes contain the port number.
        # Both address and port use network-byte order.
        offset = 0
        # Length of binary_peers should be multiple of 6
        while offset != len(binary_peers):
            b_ip = struct.unpack_from('!i', binary_peers, offset)[0]
            ip = socket.inet_ntoa(struct.pack('!i', b_ip))
            offset += 4
            port = struct.unpack_from('!H', binary_peers, offset)[0]
            offset += 2
            peer = '{}:{}'.format(ip, port)
            peers.append(peer)

        return peers


if __name__ == '__main__':
    filename = 'street-fighter.torrent'
    client = TorrentClient(filename)
