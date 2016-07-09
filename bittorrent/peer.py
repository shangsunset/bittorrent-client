import sys
import datetime
import time
import asyncio
import random
import struct
import logging

from bitstring import BitArray
from utils import PieceQueue

KEEPALIVE = bytes([0, 0, 0, 0])
CHOKE = bytes([0, 0, 0, 1]) + bytes([0])
UNCHOKE = bytes([0, 0, 0, 1]) + bytes([1])
INTERESTED = bytes([0, 0, 0, 1]) + bytes([2])
NOT_INTERESTED = bytes([0, 0, 0, 1]) + bytes([3])


class Peer():

    def __init__(self, host, port, torrent):
        self._reader = None
        self._writer = None
        self.choked = True
        self.address = {'host': host, 'port': port}
        self.queue = PieceQueue(torrent) # store blocks to be requested
        self.timer = datetime.datetime.now()

    @property
    def reader(self):
        return self._reader

    @property
    def writer(self):
        return self._writer

    @reader.setter
    def reader(self, reader):
        self._reader = reader

    @writer.setter
    def writer(self, writer):
        self._writer = writer

class PeerProtocol(asyncio.Protocol):

    def __init__(self, torrent):
        self.torrent = torrent
        self.logger = logging.getLogger('main.peer_protocol')
        self.data = bytes()
        # self.has_pieces = []
        # self.data_buffer = data_buffer
        # self.blocks_requested = blocks_requested
        # self.pieces_downloaded = pieces_downloaded

    def connection_made(self, transport):
        # a tuple containing (host, port)
        self.peer = transport.get_extra_info('peername')
        self.logger.info('connected with {}'.format(self.peer))
        transport.write(self._hand_shake())
        self.transport = transport
        self.timer = datetime.datetime.now()

    def data_received(self, data):

        # check if the data is a handshake message
        if data[1:20].lower() == b'bittorrent protocol':
            # info hash is 20 bytes long
            received_info_hash = data[28:48]
            if received_info_hash != self.torrent.info_hash:
                self._close_connection()
            else:
                data = data[68:]
                self.logger.info('Sending INTERESTED message to Peer {}'.format(self.peer))
                self.transport.write(INTERESTED)

        self._process_data(data)

    def connection_lost(self, exc):
        self.logger.info('disconnected...from {}'.format(self.peer))
        if exc is not None:
            self.logger.error('exc: {}'.format(exc))

    def _process_data(self, data):
        if self.data:
            self.data += data
        else:
            self.data = data

        while len(self.data) > 4:
            offset = 0
            try:
                message_length = struct.unpack('!i', self.data[0:4])[0]
            except struct.error as e:
                self.logger.info(e)
                self.logger.info('data: {}, data[0:4]: {}, length: {}'.format(self.data, self.data[0:4], len(self.data[0:4])))

            offset += 4
            if len(self.data) - offset < message_length:
                # not enough data to form a message,
                # return to wait for more data
                return
            elif message_length == 0:
                self.logger.debug('Peer {} sent KEEP ALIVE message'.format(self.peer))
                return
            else:
                # a whole message is collected, handle it
                message_id = self.data[offset]
                payload = self.data[offset+1:offset+message_length] if message_length > 1 else None

                self._message_handler(message_id, payload)

                offset += message_length
                self.data = self.data[offset:]

    def _message_handler(self, message_id, payload):
        """ identity type of message sent from peer and make action accordingly """

        if message_id == 0:
            self.logger.debug('Peer {} sent CHOKE message'.format(self.peer))

        elif message_id == 1:
            self.logger.debug('Peer {} sent UNCHOKE message'.format(self.peer))
            # self._send_request_msg()

        elif message_id == 2:
            self.logger.debug('Peer {} sent INTERESTED message'.format(self.peer))

        elif message_id == 3:
            self.logger.debug('Peer {} sent NOT INTERESTED message'.format(self.peer))

        elif message_id == 4:
            # peer tells what other pieces it has
            # we need to update our record
            self.logger.debug('Peer {} sent HAVE message'.format(self.peer))
            # index = struct.unpack('!i', payload)[0]
            # self.logger.info('Peer {} has piece {}'.format(self.peer, index))
            # self.has_pieces[index] = True

        elif message_id == 5:
            # message payload is what pieces the peer has, labeled by indexes
            # we need to keep a record of what the peer has
            self.logger.debug('Peer {} sent BITFIELD message'.format(self.peer))
            # self.has_pieces = BitArray(payload)

        elif message_id == 6:
            self.logger.debug('Peer {} sent REQUEST message'.format(self.peer))

        elif message_id == 7:
            self.logger.debug('Peer {} sent PIECE message'.format(self.peer))
            # self._handle_piece_msg(payload)

        elif message_id == 8:
            self.logger.debug('Peer {} sent CANCEL message'.format(self.peer))

    def _close_connection(self):
        self.transport.close()

    def _send_request_msg(self):
        """
        if the peer has this piece, request it block by block.
        last block of piece needs to calculated if piece cant
        be evenly divided
        """
        for index, piece in enumerate(self.has_pieces):
            if piece:
                message_id = b'\x06'
                message_length = bytes([0, 0, 0, 13])
                piece_length = self.torrent.info['piece length']
                request_length = self.torrent.REQUEST_LENGTH

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
                        self.transport.write(msg)
                        # self.logger.info('requesting block, index - {}, offset - {}'.format(index, begin_offset))
                        self.blocks_requested[index].append(begin_offset)

                    # if piece_length can be evenly divided by self.torrent.REQUEST_LENGTH
                    if piece_length % request_length == 0:
                        begin_offset += self.torrent.REQUEST_LENGTH
                    else:
                        if piece_length - begin_offset < request_length:
                            request_length = piece_length - begin_offset
                        else:
                            begin_offset += self.torrent.REQUEST_LENGTH

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
