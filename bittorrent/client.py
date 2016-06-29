import struct
import sys
import asyncio
import time
import socket
import logging
import datetime

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
        self.active_peers = []
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

    async def keep_alive(self):
        await asyncio.gather(
                *[self._send_keepalive_to_peer(peer) for peer in self.peers],
                )

    async def _send_keepalive_to_peer(self, peer):
        while True:
            await asyncio.sleep(90)
            if peer in self.active_peers:
                try:
                    peer.writer.write(KEEPALIVE)
                    self.logger.info('just sent keep alive message to {}'.format(peer.ip))
                except (IOError, TimeoutError, Exception) as e:
                    self.logger.error('keep live: {}'.format(e))
                    if e == 'Connection lost':
                        self.active_peers.remove(peer)
                        self.logger.info('connected peers: {}'.format(self.active_peers))

                    break

    async def _connect_to_peer(self, peer):

        try:
            reader, writer = await asyncio.open_connection(
                    peer.ip['host'], peer.ip['port'])

            peer.reader = reader
            peer.writer = writer

            await self._connection_handler(peer)
        except (ConnectionRefusedError,
                ConnectionResetError,
                ConnectionAbortedError,
                TimeoutError, OSError) as e:
            self.logger.error('{}, {}'.format(e, peer.ip))


    async def _connection_handler(self, peer):
        self.logger.info('connected with peer {}'.format(peer.ip))
        self.active_peers.append(peer)
        self.timer = datetime.datetime.now()
        peer.writer.write(self._hand_shake())
        try:
            await peer.writer.drain()
        except (IOError, Exception) as e:
            self.logger.error('hand shake: {}'.format(e))

        hand_shake_msg = b''

        while len(hand_shake_msg) < 68:
        # 68 is the length of hand shake message
            try:
                chunk = await peer.reader.read(68)
                hand_shake_msg += chunk
                if not chunk:
                    break
                info_hash = hand_shake_msg[28:48]
                if self.torrent.info_hash != info_hash:
                    self._close_connection(peer)
                else:
                    peer.writer.write(INTERESTED)
                    await peer.writer.drain()
                    self.logger.info('Sent INTERESTED message to Peer {}'.format(peer.ip))

                await self._read_from_peer(peer)
            except (Exception, IOError, ConnectionResetError) as e:
                self.logger.info('read hand shake: {}'.format(e))
                break


    async def _read_from_peer(self, peer):
        while True:

            message_body = b''
            first_4_bytes = b''
            while len(first_4_bytes) < 4:
                try:
                    chunk = await peer.reader.read(4 - len(first_4_bytes))
                except (IOError, TimeoutError, Exception) as e:
                    self.logger.error('read from peer Exception: {}'.format(e))
                    return

                if not chunk:
                    return
                first_4_bytes += chunk

            message_length = struct.unpack('!i', first_4_bytes)[0]

            if message_length == 0:
                peer.timer = datetime.datetime.now()
                self.logger.debug('Peer {} sent KEEP ALIVE message'.format(peer.ip))
            else:

                while len(message_body) < message_length:
                    try:
                        message_body_chunk = await peer.reader.read(message_length - len(message_body))
                    except (Exception, IOError) as e:
                        self.logger.info('read message body: {}'.format(e))
                        return
                    if not message_body_chunk:
                        return
                    message_body += message_body_chunk

                message_id = message_body[0]
                payload = message_body[1:]
                await self._parse_message(peer, message_id, payload)

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
        i = 0
        total_length = 0
        for index, piece in enumerate(peer.has_pieces):
            if piece:
                i += 1
                message_id = b'\x06'
                message_length = bytes([0, 0, 0, 13])
                piece_length = self.torrent.info['piece length']
                request_length = REQUEST_LENGTH

                # requesting a piece from a peer.
                begin_offset = 0
                while begin_offset < piece_length:

                    if begin_offset not in self.blocks_requested[index]:

                        msg = b''.join([
                            message_length,
                            message_id,
                            struct.pack('!i', index),
                            struct.pack('!i', begin_offset),
                            struct.pack('!i', request_length)
                            ])

                        try:
                            peer.writer.write(msg)
                            await peer.writer.drain()
                        except (IOError, TimeoutError, Exception) as e:
                            self.logger.error('send request: {}'.format(e))
                            break
                        self.blocks_requested[index].append(begin_offset)

                    # if piece_length can be evenly divided by REQUEST_LENGTH
                    if piece_length % request_length == 0:
                        begin_offset += request_length
                    else:
                        if piece_length - begin_offset < request_length:
                            request_length = piece_length - begin_offset
                            self.logger.info('this is last block of piece {}, requested length is {}'.format(index, piece_length - begin_offset))
                        else:
                            begin_offset += REQUEST_LENGTH

                    total_length += request_length
                    self.logger.info('total length requested {}'.format(total_length))
            else:
                self.logger.info('Peer doesnt have this piece {}'.format(index))
        self.logger.info('done requesting picese from {}, peer has {} pieces, total length {}'.format(peer.ip, i, total_length))
        time.sleep(20)
        self.logger.info(self.torrent.file_length())


    def _handle_piece_msg(self, message_payload):
        """ save blocks sent from peer """

        index = struct.unpack('!i', message_payload[:4])[0]
        begin_offset = struct.unpack('!i', message_payload[4:8])[0]
        block = message_payload[8:]

        self.logger.debug('saving block for piece {}'.format(index))
        try:
            downloaded_piece_index = self.data_buffer.save(index, begin_offset, block)
        except Exception as e:
            self.logger.error('save to buffer: {}'.format(e))
        self.logger.info('saved the block the buffer')

        if downloaded_piece_index is not None:
            self.pieces_downloaded.append(index)
            self.logger.info('We have piece {}'.format(downloaded_piece_index))
            self.logger.info('how many now: {}, total: {}'.format(len(self.pieces_downloaded), self.torrent.number_of_pieces))


    def _close_connection(self, peer):
        self.active_peers.remove(peer)
        peer.writer.close()
