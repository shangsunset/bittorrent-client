import logging
import asyncio

from client import TorrentClient

logger = logging.getLogger('main')
logger.setLevel(logging.DEBUG)

# create console handler with a higher log level
fh = logging.FileHandler('bittorrent.log')
ch = logging.StreamHandler()
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)


def main():
    loop = asyncio.get_event_loop()

    filename = '../street-fighter.torrent'
    client = TorrentClient(filename, loop)

    try:
        loop.run_until_complete(client._connect_to_peers())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == '__main__':
    main()
