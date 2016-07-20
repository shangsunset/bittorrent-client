import struct
import sys
import os
import asyncio
import time
from hashlib import sha1
import socket
import logging
import datetime

import requests
from bcoding import bdecode

from tracker import Tracker
from torrent import Torrent
from peer import Peer, PeerProtocol
from utils import Pieces

KEEPALIVE = bytes([0, 0, 0, 0])
CHOKE = bytes([0, 0, 0, 1]) + bytes([0])
UNCHOKE = bytes([0, 0, 0, 1]) + bytes([1])
INTERESTED = bytes([0, 0, 0, 1]) + bytes([2])
NOT_INTERESTED = bytes([0, 0, 0, 1]) + bytes([3])


class TorrentClient():

    def __init__(self, torrent_file, download_destination, loop):
        self.logger = logging.getLogger('main.torrent_client')
        self.loop = loop
        self.torrent = Torrent(torrent_file)
        self.download_destination = download_destination
        self.files_info = self.torrent.get_files_info()
        self.dest_path = self.create_dir(self.files_info)
        self.pieces = Pieces(self.torrent) # save downloaded pieces
        self.pieces_downloaded = [] # keep track blocks that are requested
        tracker = Tracker(self.torrent)
        peers_list = tracker.connect()
        self.peers = [Peer(p['hostname'], p['port'], self.torrent)
                for p in peers_list]
        self.active_peers = []

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
                if not peer.writer.transport.is_closing():
                    try:
                        peer.writer.write(KEEPALIVE)
                        peer.writer.drain()
                        self.logger.info('just sent keep alive message to {}'.format(peer.address))
                    except Exception as e:
                        self.logger.error('keep live: {}'.format(e))
                else:
                    self.logger.debug('connection closed by {}'.format(peer.address))
                    self._close_connection(peer)

    async def _connect_to_peer(self, peer):

        try:
            reader, writer = await asyncio.open_connection(
                    peer.address['host'], peer.address['port'])

            peer.reader = reader
            peer.writer = writer

            await self._connection_handler(peer)
            await self._receive_data(peer)
        except (ConnectionRefusedError,
                ConnectionResetError,
                ConnectionAbortedError,
                TimeoutError, OSError) as e:
            self.logger.error('{}, {}'.format(e, peer.address))

    async def _connection_handler(self, peer):
        self.logger.info('connected with peer {}'.format(peer.address))
        self.active_peers.append(peer)
        self.timer = datetime.datetime.now()
        try:
            peer.writer.write(self._hand_shake())
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
                    self.logger.info('read hand shake refused')
                    self._close_connection(peer)
                else:
                    peer.writer.write(INTERESTED)
                    await peer.writer.drain()
                    self.logger.info('Sent INTERESTED message to Peer {}'.format(peer.address))
            except (ConnectionRefusedError, TimeoutError, Exception) as e:
                self.logger.info(e)
                break

    async def _receive_data(self, peer):
        while True:
            message_body = b''
            first_4_bytes = b''
            while len(first_4_bytes) < 4:
                try:
                    chunk = await peer.reader.read(4 - len(first_4_bytes))
                except Exception as e:
                    self.logger.error('read from peer Exception')
                    self.logger.error(e)
                    return

                if not chunk:
                    return
                first_4_bytes += chunk

            # self.logger.info('first 4 bytes: {}'.format(first_4_bytes))
            message_length = struct.unpack('!i', first_4_bytes)[0]

            if message_length == 0:
                peer.timer = datetime.datetime.now()
                self.logger.debug('Peer {} sent KEEP ALIVE message'.format(peer.address))
            else:
                while len(message_body) < message_length:
                    try:
                        message_body_chunk = await peer.reader.read(message_length - len(message_body))
                    except Exception as e:
                        self.logger.info('read message body')
                        self.logger.error(e)
                        return
                    if not message_body_chunk:
                        return
                    message_body += message_body_chunk
                # self.logger.info('message body: {}'.format(message_body))

                message_id = message_body[0]
                payload = message_body[1:]
                await self._message_handler(peer, message_id, payload)

    async def _message_handler(self, peer, msg_id, payload):
        """ identity type of message sent from peer and make action accordingly """

        if msg_id == 0:
            self.logger.debug('Peer {} sent CHOKE message'.format(peer.address))

        elif msg_id == 1:
            self.logger.debug('Peer {} sent UNCHOKE message'.format(peer.address))
            peer.choked = False
            await self._request_piece(peer)

        elif msg_id == 2:
            self.logger.debug('Peer {} sent INTERESTED message'.format(peer.address))

        elif msg_id == 3:
            self.logger.debug('Peer {} sent NOT INTERESTED message'.format(peer.address))

        elif msg_id == 4:
            # peer tells what other pieces it has
            # we need to update our record
            self.logger.debug('Peer {} sent HAVE message'.format(peer.address))
            index = struct.unpack('!i', payload)[0]
            self.logger.info('{} has piece {}'.format(peer.address['host'], index))
            no_pieces = len(peer.queue) == 0
            peer.queue.add(index)
            if no_pieces:
                await self._request_piece(peer)

        elif msg_id == 5:
            # message payload is what pieces the peer has, labeled by indexes
            # we need to keep a record of what the peer has
            self.logger.debug('Peer {} sent BITFIELD message'.format(peer.address))
            no_pieces = len(peer.queue) == 0
            # peer.pieces = BitArray(payload)
            b = bytearray(payload)
            bitstring = ''.join([bin(x)[2:] for x in b])
            pieces_indexes = [i for i, x in enumerate(bitstring) if x == '1']
            for index in pieces_indexes:
                peer.queue.add(index)

            self.logger.info('{} has {}'.format(peer.address['host'], pieces_indexes))
            if no_pieces:
                await self._request_piece(peer)

        elif msg_id == 6:
            self.logger.debug('Peer {} sent REQUEST message'.format(peer.address))

        elif msg_id == 7:
            # self.logger.debug('Peer {} sent PIECE message'.format(peer.address))
            await self._handle_piece_msg(payload, peer)

        elif msg_id == 8:
            self.logger.debug('Peer {} sent CANCEL message'.format(peer.address))

    def _request_message(self, block):
        message_id = b'\x06'
        message_length = bytes([0, 0, 0, 13])

        msg = b''.join([
            message_length,
            message_id,
            struct.pack('!I', block['index']),
            struct.pack('!I', block['begin_offset']),
            struct.pack('!I', block['request_length'])
            ])

        return msg

    async def _request_piece(self, peer):

        if not peer.choked:
            while len(peer.queue) > 0:
                index_left = set()
                for b in peer.queue.queue:
                    index_left.add(b['index'])
                self.logger.info('peer queue {}'.format(index_left))
                self.logger.info('{} blocks left to request from {}'.format(len(peer.queue.queue), peer.address['host']))
                block = peer.queue.pop()
                self.logger.info(block)
                if self.pieces.needed(block):
                    try:
                        peer.writer.write(self._request_message(block))
                        await peer.writer.drain()
                    except Exception as e:
                        self.logger.error(e)
                    self.logger.info('requested {} from {}'.format(block, peer.address['host']))
                    self.pieces.add_requested(block)
                    break

    async def _handle_piece_msg(self, message_payload, peer):
        """ save blocks sent from peer """

        index = struct.unpack('!i', message_payload[:4])[0]
        begin_offset = struct.unpack('!i', message_payload[4:8])[0]
        payload = message_payload[8:]
        block = {
            'index': index,
            'begin_offset': begin_offset,
            'request_length': len(payload),
            'payload': payload
        }

        self.logger.info('got a block from {}, {}, {}'.format(peer.address, block['index'], block['begin_offset']))
        piece_index, piece = self.pieces.add_received(block)

        if piece is not None:
            hashed_piece = sha1(piece).digest()
            # self.logger.info(self.torrent.piece_hash_list[piece_index])
            # self.logger.info(hashed_piece)
            if self.torrent.piece_hash_list[piece_index] == hashed_piece:
                self.pieces_downloaded.append(piece_index)

                # self.write_data(piece, peer)
                self.logger.info('we have piece {}'.format(piece_index))
                self.logger.info('downloaded: {}, total: {}'.format(len(self.pieces_downloaded), self.torrent.number_of_pieces))
                # self.logger.info('percentage {:.2f}%'.format((len(self.pieces_downloaded) * 100) / self.torrent.number_of_pieces))
            else:
                self.logger.debug('discarding piece {} ***********************'.format(piece_index))
                self.pieces.discard_piece(piece_index)
                for p in self.active_peers:
                    p.queue.add(piece_index)

        if self.pieces.end_game_mode:
            await asyncio.gather(
                    *[self._request_piece(peer) for peer in self.active_peers]
                    )
        else:
            await self._request_piece(peer)

    def write_data(self, piece, peer):

        if 'length' in self.torrent.info:
            name = self.torrent.info['name']
        else:
            self.write_multi_files(piece, peer)

    def write_single_file(self, name):
        pass

    def create_dir(self, files_info):
        dirname = files_info['dirname']
        files = files_info['files']
        dest_path = os.path.join(
                os.path.expanduser(self.download_destination), dirname)
        if not os.path.exists(dest_path):
            os.makedirs(dest_path)

        return dest_path

    def write_multi_files(self, payload, peer):
        files = self.files_info['files']
        for index, f in enumerate(files):
            if not f['done']:
                if f['length'] < len(payload):
                    with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
                        little_chunk = payload[:f['length']]
                        new_file.seek(f['length_written'])
                        new_file.write(little_chunk)
                        f['length_written'] = len(little_chunk)
                    with open(os.path.join(self.dest_path, files[index+1]['name']), 'ab') as next_file:
                        remaining_chunk = payload[f['length']:]
                        next_file.seek(files[index+1]['length_written'])
                        next_file.write(remaining_chunk)
                        files[index+1]['length_written'] = len(remaining_chunk)

                elif f['length'] - f['length_written'] < len(payload):
                    with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
                        last_chunk = payload[:f['length'] - f['length_written']]
                        new_file.seek(f['length_written'])
                        new_file.write(last_chunk)
                        f['length_written'] += len(last_chunk)
                        self.logger.debug('wrote last chunk to file')
                    with open(os.path.join(self.dest_path, files[index+1]['name']), 'ab') as next_file:
                        remaining_chunk = payload[f['length'] - f['length_written']:]
                        next_file.seek(files[index+1]['length_written'])
                        next_file.write(remaining_chunk)
                        files[index+1]['length_written'] = len(remaining_chunk)

                else:
                    with open(os.path.join(self.dest_path, f['name']), 'wb') as new_file:
                        new_file.seek(f['length_written'])
                        new_file.write(payload)
                        f['length_written'] += len(payload)

                self.logger.info('file: {}, file length: {}, length written {}'.format(f['name'], f['length'], f['length_written'], peer.address['host']))
                if f['length'] == f['length_written']:
                    self.logger.info('finished file {}'.format(f['name']))
                    f['done'] = True
                break

    def _close_connection(self, peer):
        self.active_peers.remove(peer)
        peer.writer.close()
