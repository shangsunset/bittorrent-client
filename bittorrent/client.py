import struct
import sys
import asyncio
import time
import socket
import logging
import requests
from bcoding import bdecode
from torrent import Torrent
from peer import PeerProtocol
from utils import DataBuffer


class TorrentClient():

    def __init__(self, torrent_file, loop):
        self.logger = logging.getLogger('main.torrent_client')
        self.torrent = Torrent(torrent_file)
        # save downloaded pieces
        self.data_buffer = DataBuffer(self.torrent)
        # keep track blocks that are requested
        self.blocks_requested = {index: [] for index in range(self.torrent.number_of_pieces)}
        self.pieces_downloaded = []
        self.peers = self._discover_peers()
        self.loop = loop

    def _connect_to_tracker(self):
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

    def _discover_peers(self):
        """
        get peers connected to the torrent.
        peers from the tracker response is bencoded raw binary data,
        this method parses the raw binary data and returns a list of peers
        """
        tracker_response = self._connect_to_tracker()
        if 'failure reason' not in tracker_response:
            binary_peers = tracker_response['peers']
            peers = self._parse_binary_peers(binary_peers)
            return peers
        else:
            time.sleep(tracker_response['interval'])

    def _parse_binary_peers(self, binary_peers):
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

    async def _connect_to_peer(self, peer):
        try:
            asyncio.open_connection(peer['host'], peer['port'])
            # pp = PeerProtocol(
            #         self.torrent,
            #         self.data_buffer,
            #         self.blocks_requested,
            #         self.pieces_downloaded
            #         )
            # await self.loop.create_connection(
            #         lambda: pp,
            #         peer['host'],
            #         peer['port']
            #     )
            # self.protocols.append(pp)
        except ConnectionRefusedError as e:
            self.logger.info(e)
        except TimeoutError as e:
            pass

    async def connect_to_peers(self, future):
        await asyncio.gather(
                *[self._connect_to_peer(peer) for peer in self.peers],
                loop=self.loop
                )

        future.set_result('future is done!')

    # async def keep_alive(self, future):
    #     await asyncio.gather(
    #             *[protocol.send_keepalive_msg() for protocol in self.protocols],
    #             loop=self.loop
    #             )
        # return [
        #     asyncio.ensure_future(
        #         self.connect_to_peer(peer)
        #     ) for peer in self.peers
        # ]
