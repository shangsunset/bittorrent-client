import sys
import datetime
import time
import asyncio
import random
import struct
import logging

from bitstring import BitArray
from .utils import PieceQueue

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
