# Tracker

Tracker.py is a module thats used by my bit-torrent client I implemented. It talks to the tracker server to get a list of peers(seeders), so you can connect to those peers and request data from them. Peer discovery is basically the second step for implementing a bit-torrent client(first step would decoding torrent file to get torrent meta info).

You can connect to the tracker server via either HTTP or UDP, depending on the torrent file you have. Nowadays, tracker server requires you to connect via UDP. In this perticular module, it supports both HTTP and UDP connection.

`connect()` is called when the bittorrent client wants to connect to the tracker server. Since you already decoded torrent file at this point, you can find out what the scheme like so:
```python
self.torrent = torrent
self.url = self.torrent.announce_url
u = urlparse(self.url)
self.scheme = u.scheme
```
So in `connect()`, different method is invoked based on the scheme.

## Connecting via HTTP

Connecting through HTTP is easy. You just need to make a `GET` request to the tracker server with folloing keys:

- info_hash
- peer_id
- ip
- port
- uploaded
- downloaded
- left
- event

Tracker responses are bencoded dictionaries. If a tracker response has a key `failure` reason, then that maps to a human readable string which explains why the query failed, and no other keys are required.  Otherwise, it must have two keys: `interval`, which maps to the number of seconds the downloader should wait between regular rerequests, and `peers`. `peers` maps to a list of dictionaries corresponding to peers, each of which contains the keys peer id, ip, and port, which map to the peer's self-selected ID, IP address or dns name as a string, and port number, respectively.  

So if `failure` is not in the response, simply return decoded peer list. if request failed, re-request after the `interval`.


## Connecting via UDP
Using HTTP introduces significant overhead. About 10 packets are used for a request plus response containing 50 peers and the total number of bytes used is about 1206. This overhead can be reduced significantly by using a UDP based protocol. The protocol proposed here uses 4 packets and about 618 bytes, reducing traffic by 50%. For a client, saving 1 kbyte every hour isn't significant, but for a tracker serving a million peers, reducing traffic by 50% matters a lot. An additional advantage is that a UDP based binary protocol doesn't require a complex parser and no connection handling, reducing the complexity of tracker code and increasing it's performance.

In `_connect_via_udp()`, first step is to make a connect request: `_connect_request()`. To send a message to the tracker server, you need to generate a random number as `transition_id` and `action` which is number `0`.

After converting the message to a packet, send it to the tracker server using `socket` with `hostname` and `port` provided in the torrent.

In the response from the tracker server, there is `action`, `transition_id` you generated earlier, and `connection_id`.

- Check whether the packet is at least 16 bytes.
- Check whether the transaction ID is equal to the one you chose.
- Check whether the action is connect.
- Store the connection ID for future use.

If everything matches, you can make a announce reqeust.

- Choose a random transaction ID.
- Fill the announce request structure.
- Send the packet.

After getting the announce response. Check whether the transaction ID is equal to the one you chose. Extract peers from the `announce response` if they the `transition_ids` mathch.

