import struct
import sys
import asyncio
import time
import socket
import logging

import requests
from bcoding import bdecode
from bitstring import BitArray

from torrent import Torrent
from peer import Peer
from utils import DataBuffer

KEEPALIVE = bytes([0, 0, 0, 0])
CHOKE = bytes([0, 0, 0, 1]) + bytes([0])
UNCHOKE = bytes([0, 0, 0, 1]) + bytes([1])
INTERESTED = bytes([0, 0, 0, 1]) + bytes([2])
NOT_INTERESTED = bytes([0, 0, 0, 1]) + bytes([3])

REQUEST_LENGTH = 2**14

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

    def _discover_peers(self):
        """
        get peers connected to the torrent.
        peers from the tracker response is bencoded raw binary data,
        this method parses the raw binary data and returns a list of peers
        """
        tracker_response = self._connect_to_tracker()
        if 'failure reason' not in tracker_response:
            bin_peers = tracker_response['peers']
            peers = self._parse_binary_peers(bin_peers)
            return peers
        else:
            time.sleep(tracker_response['interval'])

    def _parse_binary_peers(self, bin_peers):
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
            host = socket.inet_ntoa(struct.pack('!i', bin_ip))
            offset += 4
            port = struct.unpack_from('!H', bin_peers, offset)[0]
            offset += 2
            peer = Peer(host, port)
            # peer = {'host': host, 'port': port}
            peers.append(peer)

        return peers

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

    def _hand_shake(self):
        """ https://wiki.theory.org/BitTorrentSpecification#Handshake """

        pstrlen = 19
        pstr = 'BitTorrent protocol'
        reserved = bytes(8)

        # return a long byte string
        return b''.join([
            bytes([pstrlen]),
            bytes(pstr, encoding='utf-8'),
            reserved,
            self.torrent.info_hash,
            bytes(self.torrent.peer_id, encoding='utf-8')
        ])

    async def connect_to_peers(self):
        await asyncio.gather(
                *[self._connect_to_peer(peer) for peer in self.peers],
                )

    async def _connect_to_peer(self, peer):

        try:
            reader, writer = await asyncio.open_connection(
                    peer.ip['host'], peer.ip['port'])

            peer.reader = reader
            peer.writer = writer

        except (ConnectionRefusedError,
                ConnectionResetError,
                ConnectionAbortedError,
                TimeoutError, OSError) as e:
            self.logger.error('{}, {}'.format(e, peer.ip))

        else:
            try:
                await self._connection_handler(peer)
            except ConnectionResetError as e:
                self.logger.error(e)
                time.sleep(10)

    async def _connection_handler(self, peer):
        self.logger.info('connected with peer {}'.format(peer.ip))
        peer.writer.write(self._hand_shake())

        try:
            chunk = await peer.reader.readexactly(68)
        except asyncio.IncompleteReadError as e:
            self.logger.error(e)

        info_hash = chunk[28:48]
        if self.torrent.info_hash != info_hash:
            self._close_connection(peer)
        else:
            peer.writer.write(INTERESTED)
            self.logger.info('Sent INTERESTED message to Peer {}'.format(peer.ip))

        await self._read_from_peer(peer)

    async def _read_from_peer(self, peer):

        while True:

            message_body = b''
            first_4_bytes = b''
            # if complete_message:
            # try:
            while len(first_4_bytes) < 4:
                self.logger.info('getting message length')
                try:
                    chunk = await peer.reader.read(4 - len(first_4_bytes))
                except IOError as e:
                    self.logger.info('IOError: {}'.format(e))
                except Exception as exc:
                    self.logger.info(exc)

                if not chunk:
                    self.logger.info('no bytes read')
                    return
                first_4_bytes += chunk
                self.logger.info(first_4_bytes)

            # except asyncio.IncompleteReadError as e:
                # self.logger.error(e)
                # break

            try:
                message_length = struct.unpack('!i', first_4_bytes)[0]
            except struct.error as e:
                self.logger.info(message_length)
                sys.exit()


            if message_length == 0:
                self.logger.debug('Peer {} sent KEEP ALIVE message'.format(peer.ip))
                continue
            else:

                while len(message_body) < message_length:
                    # try:
                    self.logger.info('reading chunk in length: {}...'.format(message_length - len(message_body)))
                    message_body_chunk = await peer.reader.read(message_length - len(message_body))
                    if not message_body_chunk:
                        return
                    # self.logger.info('message body chunk {}'.format(message_body_chunk))
                    message_body += message_body_chunk
                    # except asyncio.IncompleteReadError as e:
                    #     if len(e.partial) > 0:
                    #         partial_message = e.partial
                    #         self.logger.info('partial message body len {}, partial: {}'.format(len(partial_message), partial_message))
                    #         message_body += partial_message
                    #         self.logger.info('len of message_body: {}, message_length: {}'.format(len(message_body), message_length))
                    #         time.sleep(10)
                    #
                    #         self.logger.info('need {} more, have {}'.format(message_length - len(message_body), len(message_body)))
                    #         self.logger.info('message body chunk len {}'.format(len(message_body_chunk)))

                message_id = message_body[0]
                payload = message_body[1:]
                await self._parse_message(peer, message_id, payload)
            # else:
            #     self.logger.info('finishing remaining message')
            #     self.logger.info('need {} more, have {}'.format(message_length - len(message_body), len(message_body)))
            #     time.sleep(10)
            #     try:
            #         remaining_chunk = await peer.reader.readexactly(message_length - len(message_body))
            #     except asyncio.IncompleteReadError as e:
            #         sys.exit()
            #     self.logger.info('len of remaining chunk: {}, need {}'.format(len(remaining_chunk), len(message_length) - len(message_body)))
            #     time.sleep(10)
            #     message_body += remaining_chunk
            #     if len(message_body) == message_length:
            #         complete_message = True

            # if complete_message:
            #     self.logger.info('message complete')
            #     message_id = message_body[0]
            #     payload = message_body[1:]
            #     await self._parse_message(peer, message_id, payload)
            #     message_length = 0
            #     message_body = b''

    async def _parse_message(self, peer, msg_id, payload):
        """ identity type of message sent from peer and make action accordingly """

        if msg_id == 0:
            self.logger.debug('Peer {} sent CHOKE message'.format(peer.ip))

        elif msg_id == 1:
            self.logger.debug('Peer {} sent UNCHOKE message'.format(peer.ip))
            await self._send_request_msg(peer)

        elif msg_id == 2:
            self.logger.debug('Peer {} sent INTERESTED message'.format(peer.ip))

        elif msg_id == 3:
            self.logger.debug('Peer {} sent NOT INTERESTED message'.format(peer.ip))

        elif msg_id == 4:
            # peer tells what other pieces it has
            # we need to update our record
            self.logger.debug('Peer {} sent HAVE message'.format(peer.ip))
            index = struct.unpack('!i', payload)[0]
            self.logger.info('Peer {} has piece {}'.format(peer.ip, index))
            peer.has_pieces[index] = True

        elif msg_id == 5:
            # message payload is what pieces the peer has, labeled by indexes
            # we need to keep a record of what the peer has
            self.logger.debug('Peer {} sent BITFIELD message'.format(peer.ip))
            peer.has_pieces = BitArray(payload)

        elif msg_id == 6:
            self.logger.debug('Peer {} sent REQUEST message'.format(peer.ip))

        elif msg_id == 7:
            self.logger.debug('Peer {} sent PIECE message'.format(peer.ip))
            self._handle_piece_msg(payload)

        elif msg_id == 8:
            self.logger.debug('Peer {} sent CANCEL message'.format(peer.ip))

    async def _send_request_msg(self, peer):
        """
        if the peer has this piece, request it block by block.
        last block of piece needs to calculated if piece cant
        be evenly divided
        """
        for index, piece in enumerate(peer.has_pieces):
            if piece:
                message_id = b'\x06'
                message_length = bytes([0, 0, 0, 13])
                piece_length = self.torrent.info['piece length']
                request_length = REQUEST_LENGTH

                # requesting a piece for a peer.
                begin_offset = 0
                while begin_offset < piece_length:

                    if begin_offset not in self.blocks_requested[index] and \
                        not self.data_buffer.is_block_downloaded(
                                index, begin_offset):

                        msg = b''.join([
                            message_length,
                            message_id,
                            struct.pack('!i', index),
                            struct.pack('!i', begin_offset),
                            struct.pack('!i', request_length)
                            ])
                        peer.writer.write(msg)
                        await peer.writer.drain()
                        self.blocks_requested[index].append(begin_offset)

                    # if piece_length can be evenly divided by REQUEST_LENGTH
                    if piece_length % request_length == 0:
                        begin_offset += REQUEST_LENGTH
                    else:
                        if piece_length - begin_offset < request_length:
                            request_length = piece_length - begin_offset
                            # self.logger.info('this is last block of piece {}'.format(index))
                        else:
                            begin_offset += REQUEST_LENGTH
            else:
                self.logger.info('Peer doesnt have this piece {}'.format(index))

    def _handle_piece_msg(self, message_payload):
        """ save blocks sent from peer """

        index = struct.unpack('!i', message_payload[:4])[0]
        begin_offset = struct.unpack('!i', message_payload[4:8])[0]
        block = message_payload[8:]

        downloaded_piece_index = self.data_buffer.save(index, begin_offset, block)

        if downloaded_piece_index:
            self.pieces_downloaded.append(index)
            self.logger.info('We have piece {}'.format(downloaded_piece_index))
            self.logger.info('pieces downloaded: {}'.format(self.pieces_downloaded))

    def _close_connection(self, peer):
        self.logger.info('info hash doesnt match with {}. connection closed...'.format(peer.ip))
        peer.writer.close()
    # async def keep_alive(self, future):
    #     await asyncio.gather(
    #             *[protocol.send_keepalive_msg() for protocol in self.protocols],
    #             loop=self.loop
    #             )
