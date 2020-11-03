import zmq
import threading
import logging
import uuid
from zeroconf import ServiceInfo, Zeroconf, IPVersion
import socket

class tcpConnection(threading.Thread):
    """Setups and manages a connection thread to iotdashboard via TCP."""

    def __get_local_ip_address(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def __zconf_publish_tcp(self, port):
        zconf_desc = {'ConnectionUUID': self.connection_id.hex}
        zconf_info = ServiceInfo(
            "_DashIO._tcp.local.",
            "{}._DashIO._tcp.local.".format(self.connection_id.hex),
            addresses=[socket.inet_aton(self.local_ip)],
            port=port,
            properties=zconf_desc,
            server=self.host_name + ".",
        )
        self.zeroconf.register_service(zconf_info)

    def add_device(self, device):
        device.add_connection(self.connection_id)

    def __init__(self, ip="*", port=5000, context=None):
        """
        """

        threading.Thread.__init__(self, daemon=True)
        self.context = context or zmq.Context.instance()
        self.connection_id = uuid.uuid4()
        self.b_connection_id = self.connection_id.bytes

        tx_url_internal = "inproc://TX_{}".format(self.connection_id.hex)
        rx_url_internal = "inproc://RX_{}".format(self.connection_id.hex)

        self.tx_zmq_pub = self.context.socket(zmq.PUB)
        self.tx_zmq_pub.bind(tx_url_internal)

        self.rx_zmq_sub = self.context.socket(zmq.SUB)
        self.rx_zmq_sub.bind(rx_url_internal)

        # Subscribe on ALL, and my connection
        self.rx_zmq_sub.setsockopt(zmq.SUBSCRIBE, b"ALL")
        self.rx_zmq_sub.setsockopt(zmq.SUBSCRIBE, b"ALARM")
        self.rx_zmq_sub.setsockopt(zmq.SUBSCRIBE, self.b_connection_id)

        self.tcpsocket = self.context.socket(zmq.STREAM)

        ext_url = "tcp://" + ip + ":" + str(port)
        self.tcpsocket.bind(ext_url)
        self.tcpsocket.set(zmq.SNDTIMEO, 5)

        self.poller = zmq.Poller()
        self.poller.register(self.tcpsocket, zmq.POLLIN)
        self.poller.register(self.rx_zmq_sub, zmq.POLLIN)

        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self.socket_ids = []
        self.running = True

        host_name = socket.gethostname()
        hs = host_name.split(".")
        # rename for .local mDNS advertising
        self.host_name = "{}.local".format(hs[0])

        self.local_ip = self.__get_local_ip_address()
        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self.__zconf_publish_tcp(port)
        self.start()

    def close(self):
        self.zeroconf.unregister_all_services()
        self.zeroconf.close()
        self.running = False

    def run(self):
        def __zmq_tcp_send(id, data):
            try:
                self.tcpsocket.send(id, zmq.SNDMORE)
                self.tcpsocket.send(data, zmq.NOBLOCK)
            except zmq.error.ZMQError as e:
                logging.debug("Sending TX Error: " + str(e))
                # self.socket_ids.remove(id)

        id = self.tcpsocket.recv()
        self.tcpsocket.recv()  # empty data here

        while self.running:
            socks = dict(self.poller.poll())

            if self.tcpsocket in socks:
                id = self.tcpsocket.recv()
                message = self.tcpsocket.recv()
                if id not in self.socket_ids:
                    logging.debug("Added Socket ID: " + id.hex())
                    self.socket_ids.append(id)
                logging.debug("TCP ID: %s, RX: %s", id.hex(), message.decode('utf-8').rstrip())
                if message:
                    self.tx_zmq_pub.send_multipart([self.b_connection_id, id, message])
                else:
                    if id in self.socket_ids:
                        logging.debug("Removed Socket ID: " + id.hex())
                        self.socket_ids.remove(id)
            if self.rx_zmq_sub in socks:
                [address, msg_id, data] = self.rx_zmq_sub.recv_multipart()
                if address == b'ALL':
                    for id in self.socket_ids:
                        logging.debug("TCP ID: %s, Tx: %s", id.hex(), data.decode('utf-8').rstrip())
                        __zmq_tcp_send(id, data)
                elif address == self.b_connection_id:
                    logging.debug("TCP ID: %s, Tx: %s", msg_id.hex(), data.decode('utf-8').rstrip())
                    __zmq_tcp_send(msg_id, data)

        for id in self.socket_ids:
            __zmq_tcp_send(id, b'')

        self.tcpsocket.close()
        self.tx_zmq_pub.close()
        self.rx_zmq_sub.close()
