import threading
from ss45 import ProxyServer

if __name__ == "__main__":
  #Create three proxy instances
  server1 = ProxyServer('0.0.0.0', 1091)
  server2 = ProxyServer('0.0.0.0', 1092)
  server3 = ProxyServer('0.0.0.0', 1093)

  #Run proxy instances
  threading.Thread(target = server1.start).start()
  threading.Thread(target = server2.start).start()
  threading.Thread(target = server3.start).start()

  #Create main proxy instance
  server = ProxyServer('0.0.0.0', 1088)
  #Assign proxy chanel
  server.load_proxy('socks4://127.0.0.1:1091', 'socks5://127.0.0.1:1092', 'socks4://127.0.0.1:1093')

  #Run main proxy instance
  server.start()

  #Run browser(Firefox) with socks4 or socks5, port 1088 settings
  #Enjoy browse via proxy chanels
