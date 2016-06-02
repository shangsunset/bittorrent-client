import asyncio
import struct
import logging


class PeerProtocol(asyncio.Protocol):

    def __init__(self, torrent):
        self.torrent = torrent
        self.logger = logging.getLogger('main.peer_protocol')
        self.message_buffer = bytes()

    def connection_made(self, transport):
        # a tuple containing (host, port)
        self.peer = transport.get_extra_info('peername')
        self.logger.info('connected with {}'.format(self.peer))
        transport.write(self._hand_shake())
        self.transport = transport

    def data_received(self, data):
        """
        info hash looks something like:
        b'\x13BitTorrent protocol\x00\x00\x00\x00\x00\x00
        \x00\x00#\xb0\x93\x9ez\xc8\xb9\xb0\x1c\xda\xf0\x1f
        \x98\x8b\x9f\xfb\xbeD\xdd\xe2-AS0001-059505862275'
        """

        # existing message buffer
        if self.message_buffer:
            # self.logger.info('here~~~~~~~~~~~~')
            # self.logger.info('existing buffer from {}: {}'.format(self.peer, self.message_buffer))
            self.message_buffer += data
            # self.logger.info('conactenated buffer from {}: {}'.format(self.peer, self.message_buffer))
        else:
            # self.logger.info('here++++++++++++')
            self.message_buffer = data
            # self.logger.info('new buffer from {}: {}'.format(self.peer, self.message_buffer))

        if self.message_buffer[1:20].lower() == b'bittorrent protocol':
            # info hash is 20 bytes long
            received_info_hash = data[28:48]
            if received_info_hash != self.torrent.info_hash:
                self._close_connection()
            else:
                # message that comes immediately after the hand shake
                self.message_buffer = data[68:]

        if len(self.message_buffer) >= 4:
            message_length = struct.unpack('!i', self.message_buffer[:4])[0]
            message_id = self.message_buffer[4]
            self.logger.info('{}, length: {}, buffer length: {}'.format(
                self.peer, message_length, len(self.message_buffer)
                ))

        # wait until the length of message buffer is greater or equal
        # to message_length obtained from first 4 bytes of self.message_buffer
        if len(self.message_buffer) >= message_length:
            self._read_message(self.message_buffer, message_length)


    def connection_lost(self, exc):
        self.logger.info('disconnected...from {}'.format(self.peer))
        if exc is not None:
            self.logger.error('exc: {}'.format(exc))

    def _read_message(self, message_buffer,  message_length):
        message_id = message_buffer[4]
        message_body = message_buffer[4:message_length + 1]
        self.logger.info('messages received from: {}, length: {}, body: {}'.format(
                self.peer, len(self.message_buffer), message_body))

    def _close_connection(self):
        self.transport.close()

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
