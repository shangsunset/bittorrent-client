# BitTorrent Client

DONE:

1. connecting to peers
2. http/udp tracker protocol
3. handling Bitfield, Have, Choke, Unchoke, Piece Messages
4. verifying pieces
5. downloading data from peers
6. writing to files

TODO:

1. sending out Bitfield, Have, Cancel to other peers
2. handling Request message from other peers
3. seeding

## Install:

```
git clone https://github.com/shangsunset/bittorrent-client.git && cd bittorrent-client
pip install -r requirements.txt
```
