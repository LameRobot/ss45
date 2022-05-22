# ss45

socks4 and socks5 server

## Usage

Use it for connecting to various internet services via proxy chanels.

Load into ss45 proxy(socks4 or socks5) chain for working via several tunnels.

## Example

Ordinary server
```python
from ss45 import ProxyServer

#Create proxy instance on port 1091
server = ProxyServer('0.0.0.0', 1091)

#Run proxy instance
server.start()

#Run browser via socks4(5) proxy server on port 1091
```

Server with channel. (Not real working example proxies below)
```python
from ss45 import ProxyServer

#Create proxy instance on port 1088
server = ProxyServer('0.0.0.0', 1088)

#Load proxy chanel
server.load_proxy('socks4://example.com:4153', 'socks5://example2.com:1080', 'socks4://example3.com:5678')

#Run proxy instance
server.start()

#Run browser via socks4(5) proxy server on port 1088
```
