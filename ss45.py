import threading
import socket
from datetime import datetime
import sys

class ProxyServer:
  server_socket = None
  is_debug = False
  proxy_list = [()]

  def __init__(self, host, port):
    self.set_debug(self.is_debug)
    self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server_socket.bind((host, port))

  def load_proxy(self, *proxy_list):
    self.proxy_list = []
    for e in proxy_list:
      self.proxy_list.append(self.parse_proxy(e))
    self.proxy_list.append(())
    self.log('Proxy:', len(self.proxy_list)-1, self.proxy_list)

  def parse_proxy(self, proxy):
    proto, host_port = proxy.split('://')
    host, port = host_port.split(':')
    proto = 4 if proto == 'socks4' else 5
    port = int(port)
    return host, port, proto

  def set_debug(self, state):
    self.is_debug = state
    OneMixer.is_debug = state

  def log(self, *args):
    if self.is_debug:
      t = datetime.now().time()
      inst = 'ProxyServer'
      print(f'[{t} - {inst}]', *args, flush = True)

  def start(self):
    self.server_socket.listen()
    while True:
      self.log('Start listen')
      try:
        socket, addr = self.server_socket.accept()
      except Exception as e:
        self.log('Connection error:', str(e))
        continue
      self.log('Connection Ok')
      instance = OneMixer(socket, self.proxy_list)
      th = threading.Thread(target = instance.start)
      th.start()
      self.log('End')

class OneMixer:
  is_established = False
  is_debug = False
  proxy_list = [()]
  proxy_count = 0

  def __init__(self, socket, proxy_list):
    self.proxy_list = proxy_list
    self.proxy_count = len(proxy_list) - 1

    self.master = PrimeSocket(self, socket)
    self.slave = PrimeSocket(self, None)
    self.set_debug(self.is_debug)

  def set_debug(self, state):
    self.is_debug = state
    self.master.is_debug = self.is_debug
    self.slave.is_debug = self.is_debug

  def log(self, *args):
    if self.is_debug:
      t = datetime.now().time()
      inst = 'Mixer'
      print(f'[{t} - {inst}]', *args, flush = True)

  def start(self):
    self.master.start()

  def close_signal(self):
    self.is_established = False
    self.master.close()
    self.slave.close()

  def master_wait(self):
    proto = Protocol45.get_proto(self.master.data)
    if not proto:
      return
    self.master.proto = proto
    if proto == 5:
      data = Protocol45.auth5_confirmation()
      if self.master.send(data) == False: return
      self.log('send', data)
      return self.socks5_auth_master
    return self.master_chain()

  def socks5_auth_master(self):
    proto = Protocol45.socks5_auth_ok(self.master.data)
    if not proto:
      return self.master_wait
    return self.master_chain()

  def master_chain(self):
    target_host, target_port = Protocol45.get_host_port(self.master.data, self.master.proto)
    self.proxy_list[-1] = (target_host, target_port, self.master.proto)
    self.proxy_idx = 0
    if self.proxy_count == 0:
      self.slave_make_connection()
      data = Protocol45.confirmation_answer(self.slave.is_connected, self.slave.proto)
      if self.master.send(data) == False: return
      self.log('send', data)
      if self.master.is_connected and self.slave.is_connected:
        self.is_established = True
        return self.master_transparent
      else:
        self.is_established = False
        self.close_signal()
      return self.master_wait
    if self.proxy_count >= 1:
      rez = self.slave_wait()
      if rez:
        self.slave.fsm_state = rez
        return self.master_transparent
      else:
        return self.master_wait
    return

  def slave_make_connection(self):
    self.slave.host, self.slave.port, self.slave.proto = self.proxy_list[0]
    self.slave.start()

  def slave_wait(self):
    if self.proxy_count == 0:
      return self.slave_transparent()
    if self.proxy_count >= 1:
      self.slave_make_connection()
      if self.slave.is_connected:
        return self.slave_process()
      else:
        self.close_signal()
    return

  def slave_process(self):
    self.proxy_idx += 1
    if self.slave.proto == 5:
      data = Protocol45.auth5_request()
      if self.slave.send(data) == False: return
      self.log('send', data)
      return self.socks5_auth_slave
    else:
      data = Protocol45.buid_connect_data(self.proxy_list[self.proxy_idx][0], self.proxy_list[self.proxy_idx][1], self.slave.proto)
      if self.slave.send(data) == False: return
      self.log('send', data)
      return self.slave_chain

  def socks5_auth_slave(self):
    if self.slave.data != Protocol45.auth5_confirmation():
      return self.slave_wait
    data = Protocol45.buid_connect_data(self.proxy_list[self.proxy_idx][0], self.proxy_list[self.proxy_idx][1], self.slave.proto)
    if self.slave.send(data) == False: return
    self.log('send', data)
    return self.slave_chain

  def slave_chain(self):
    if self.proxy_count == 0:
      print('wtf?')
      pass
    elif self.proxy_count >= 1:
      is_established = Protocol45.is_connection_established(self.slave.data, self.slave.proto)
      if self.proxy_count == self.proxy_idx:
        self.is_established = is_established
        data = Protocol45.confirmation_answer(self.is_established, self.proxy_list[-1][2])
        if self.master.send(data) == False:
          self.is_established = False
          return
        self.log('send', data)
        if self.is_established:
          self.log('Info', self.proxy_count, self.proxy_list)
          return self.slave_transparent
        else:
          return self.slave_wait
      else:
        self.slave.host, self.slave.port, self.slave.proto = self.proxy_list[self.proxy_idx]
        self.log('Next proxy', self.proxy_idx)
        return self.slave_process()

  def transparent(self, inp, out):
    data = inp.data
    if out.send(data) == False: return
    out.log('send', data)
         
  def master_transparent(self):
    if self.is_established:
      self.transparent(self.master, self.slave)
    return self.master_transparent

  def slave_transparent(self):
    if self.is_established:
      self.transparent(self.slave, self.master)
    return self.slave_transparent

class PrimeSocket:
  socket = None
  is_connected = False
  timeout = 1
  is_debug = False
  fsm_state = None

  def __init__(self, parent, socket):
    self.parent = parent
    self.socket = socket
    if socket:
      self.fsm_state = self.parent.master_wait
      self.name = 'Server'
    else:
      self.fsm_state = self.parent.slave_wait
      self.name = 'Client'

  def log(self, *args):
    if self.is_debug:
      t = datetime.now().time()
      print(f'[{t} - {self.name}]', *args, flush = True)

  def start(self):
    self.log('Start')
    if self.open():
      th = threading.Thread(target = self.callback)
      th.start()
    self.log('End')

  def callback(self):
    self.log('Callback start')
    try:
      self.socket.settimeout(self.timeout)
    except Exception as e:
      self.log('Settimeout:', str(e))
    while self.is_connected:
      self.data = self.recv()
      if self.data == False: continue
      if self.data and (self.data != b''):
        self.log('recv', self.data)
        self.fsm()
    self.close()
    self.log('Callback end')

  def fsm(self):
    ret = self.fsm_state()
    if ret:
      self.fsm_state = ret

  def send(self, data):
    if not self.is_connected: return False
    try:
      self.socket.send(data)
    except Exception as e:
      self.log('Send error:', str(e))
      self.close()
      return False
    return True

  def recv(self):
    if not self.is_connected: return False
    try:
      data = self.socket.recv(1024)
    except Exception as e:
      if e.errno == None:
        return False
      self.log('Recv error:', str(e))
      self.close()
      return False
    if data == b'':
      self.log('Recv disconnect')
      self.close()
      return False
    return data

  def open(self):
    if self.socket:
      self.is_connected = True
      return True
    self.log('Begin connection')
    try:
      self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      self.socket.connect((self.host, self.port))
    except Exception as e:
      self.log('Connection error:', str(e))
      self.is_connected = False
      return False
    self.log('Connection Ok')
    self.is_connected = True
    return True

  def close(self):
    if self.is_connected:
      try:
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()
      except Exception as e:
        self.log('Shutdown error', str(e))
      self.is_connected = False
      self.parent.close_signal()

class Protocol45:
  def confirmation_answer(is_connected, proto):
    if is_connected:
      data = b'\x00Z\x00\x00\x00\x00\x00\x00' if (proto == 4) else b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00'
    else:
      data = b'\x00[\x00\x00\x00\x00\x00\x00' if (proto == 4) else b'\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00'
    return data

  def auth5_request():
      return b'\x05\x01\x00'

  def auth5_confirmation():
      return b'\x05\x00'

  def is_connection_established(data, proto):
    if proto == 4:
      rez = (len(data) == 8) and (data[0] == 0) and (data[1] == 90)
    else:
      rez = (len(data) == 10) and (data[:4] == b'\x05\x00\x00\x01')
    return rez

  def get_proto(data):
    if (len(data) == 9) and (data[:2] == b'\x04\x01') and (data[-1] == 0):
      return 4
    if (len(data) == 3) and (data[:3] == b'\x05\x01\x00'):
      return 5
    return 0

  def get_host_port(data, proto):
    host = socket.inet_ntoa(data[4:8])
    port = int.from_bytes(data[2:4] if (proto == 4) else data[8:10], 'big')
    return host, port

  def socks5_auth_ok(data):
    if (len(data) == 10) and (data[:4] == b'\x05\x01\x00\x01'):
      return 5
    return 0

  def buid_connect_data(host, port, proto):
    socks_ip = bytes(int(e) for e in host.split('.'))
    socks_port = bytes((port//256, port%256))
    return b'\x04\x01' + socks_port + socks_ip + b'\x00' if proto == 4 else b'\x05\x01\x00\x01' + socks_ip + socks_port

if __name__ == "__main__":
  port = 1088
  if len(sys.argv) == 2:
    port = int(sys.argv[1])

  server = ProxyServer('0.0.0.0', port)
  server.set_debug(False)
#  server.load_proxy('socks4://127.0.0.1:1091', 'socks5://127.0.0.1:1092', 'socks4://127.0.0.1:1093')
#  server.load_proxy('socks4://127.0.0.1:1091', 'socks5://127.0.0.1:1092')
#  server.load_proxy('socks4://127.0.0.1:1091')

  server.start()
