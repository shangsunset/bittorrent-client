import struct
import time
import socket
import asyncio
import requests
from bcoding import bdecode
from torrent import Torrent

from peer_protocol import PeerProtocol

class TorrentClient():

    def __init__(self, torrent_file, loop):
        self.torrent = Torrent(torrent_file)
        self.peers = self.get_peers()
        self.loop = loop

    def connect_to_tracker(self):
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

        r = requests.get(self.torrent.tracker_url, params=keys)
        response = bdecode(r.content)
        return response

    def get_peers(self):
        """
        get peers connected to the torrent.
        peers from the tracker response is bencoded raw binary data,
        this method parses the raw binary data and returns a list of peers
        """
        tracker_response = self.connect_to_tracker()
        if 'failure reason' not in tracker_response:
            binary_peers = tracker_response['peers']
            peers = self.parse_binary_peers(binary_peers)
            return peers
        else:
            time.sleep(tracker_response['interval'])

    def parse_binary_peers(self, binary_peers):
        """
        The first 4 bytes contain the 32-bit ipv4 address.
        The remaining two bytes contain the port number.
        Both address and port use network-byte order.
        """
        offset = 0
        peers = []
        # Length of binary_peers should be multiple of 6
        while offset != len(binary_peers):
            b_ip = struct.unpack_from('!i', binary_peers, offset)[0]
            host = socket.inet_ntoa(struct.pack('!i', b_ip))
            offset += 4
            port = struct.unpack_from('!H', binary_peers, offset)[0]
            offset += 2
            peer = {'host': host, 'port': port}
            peers.append(peer)

        return peers

    async def connect_to_peer(self, peer):
        try:
            await self.loop.create_connection(
                    lambda: PeerProtocol(self.torrent),
                    peer['host'],
                    peer['port']
                )
        except ConnectionRefusedError as e:
            print(e)
        except TimeoutError as e:
            pass

    def connect_to_peers(self):
        # await asyncio.gather(
        #         *[self.connect_to_peer(peer) for peer in self.peers],
        #         self.loop
        #         )

        return [
            asyncio.ensure_future(
                self.connect_to_peer(peer)
            ) for peer in self.peers
        ]


def main():
    loop = asyncio.get_event_loop()

    filename = 'street-fighter.torrent'
    client = TorrentClient(filename, loop)

    try:
        loop.run_until_complete(asyncio.wait(client.connect_to_peers()))
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == '__main__':
    main()
