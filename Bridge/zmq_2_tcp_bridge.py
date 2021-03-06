import zmq
import threading
import logging
import time
import socket
import signal

from zeroconf import IPVersion, ServiceInfo, Zeroconf, ServiceBrowser


class ZeroConfListener:
    def __init__(self, context=None):
        self.context = context or zmq.Context.instance()
        self.zmq_socket = self.context.socket(zmq.PUSH)
        self.zmq_socket.bind("inproc://zconf")

    def remove_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            for address in info.addresses:
                self.zmq_socket.send_multipart([name.encode('utf-8'), b"remove", socket.inet_ntoa(address).encode('utf-8'), info.properties[b'sub_port'], info.properties[b'pub_port']])

    def add_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            for address in info.addresses:
                self.zmq_socket.send_multipart([name.encode('utf-8'), b"add", socket.inet_ntoa(address).encode('utf-8'), info.properties[b'sub_port'], info.properties[b'pub_port']])

    def update_service(self, zeroconf, type, name):
        info = zeroconf.get_service_info(type, name)
        if info:
            for address in info.addresses:
                self.zmq_socket.send_multipart([name.encode('utf-8'), b"update", socket.inet_ntoa(address).encode('utf-8'), info.properties[b'sub_port'], info.properties[b'pub_port']])


class zmq_tcpBridge(threading.Thread):
    """Setups and manages a connection thread to iotdashboard via TCP."""

    def connect_zmq_device(self, name, ip_address, sub_port, pub_port):
        if name not in self.devices:
            self.devices.append(name)
            logging.debug("Connect: %s, %s, %s, %s", name.decode('utf-8'), ip_address.decode('utf-8'), sub_port.decode('utf-8'), pub_port.decode('utf-8'))
            tx_url = "tcp://{}:{}".format(ip_address.decode('utf-8'), sub_port.decode('utf-8'))
            rx_url = "tcp://{}:{}".format(ip_address.decode('utf-8'), pub_port.decode('utf-8'))

            self.tx_zmq_pub.connect(tx_url)
            self.rx_zmq_sub.connect(rx_url)

    def disconnect_zmq_device(self, name, ip_address, sub_port, pub_port):
        if name in self.devices:
            self.devices.remove(name)
            tx_url = "tcp://{}:{}".format(ip_address, sub_port)
            rx_url = "tcp://{}:{}".format(ip_address, pub_port)

            self.tx_zmq_pub.disconnect(tx_url)
            self.rx_zmq_sub.disconnect(rx_url)

        #  Badness 10000
    def __get_local_ip_address(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]

    def __zconf_publish_tcp(self, port):
        zconf_desc = {'deviceID': self.device_id,
                      'deviceType': self.device_type,
                      'deviceName': self.device_name}
        zconf_info = ServiceInfo(
            "_DashIO._tcp.local.",
            "Bridge-{}._DashIO._tcp.local.".format(port),
            addresses=[socket.inet_aton(self.local_ip)],
            port=port,
            properties=zconf_desc,
            server=self.host_name + ".",
        )
        self.zeroconf.register_service(zconf_info)
        self.zero_service_list.append(zconf_info)

    def __init__(self, tcp_port=5000, context=None):
        """
        """

        threading.Thread.__init__(self, daemon=True)

        self.device_id = "3141592654"
        self.device_type = "TCPBridge"
        self.device_name = "MulipleTCP"
        self.local_ip = self.__get_local_ip_address()
        self.ext_url = "tcp://" + self.local_ip + ":" + str(tcp_port)
        self.host_name = socket.gethostname()
        hs = self.host_name.split(".")
        # rename for .local mDNS advertising
        self.host_name = "{}.local".format(hs[0])
        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self.zero_service_list = []
        self.__zconf_publish_tcp(tcp_port)

        logging.debug("HostName: %s", self.host_name)
        logging.debug("      IP: %s", self.local_ip)

        self.context = context or zmq.Context.instance()

        self.socket_ids = []
        self.devices = []
        self.running = True
        self.start()

    def close(self):
        for id in self.socket_ids:
            self._zmq_send(id, "")
        self.zeroconf.unregister_all_services()
        self.zeroconf.close()
        self.running = False

    def run(self):
        self.tx_zmq_pub = self.context.socket(zmq.PUB)
        self.rx_zmq_sub = self.context.socket(zmq.SUB)
        self.rx_zmq_sub.setsockopt(zmq.SUBSCRIBE, b'')

        rx_zconf_pull = self.context.socket(zmq.PULL)
        rx_zconf_pull.connect("inproc://zconf")

        # Subscribe on ALL, and my connection

        self.tcpsocket = self.context.socket(zmq.STREAM)
        self.tcpsocket.bind(self.ext_url)
        self.tcpsocket.set(zmq.SNDTIMEO, 5)

        poller = zmq.Poller()
        poller.register(self.tcpsocket, zmq.POLLIN)
        poller.register(self.rx_zmq_sub, zmq.POLLIN)
        poller.register(rx_zconf_pull, zmq.POLLIN)

        def __zmq_tcp_send(id, data):
            try:
                self.tcpsocket.send(id, zmq.SNDMORE)
                self.tcpsocket.send(data, zmq.NOBLOCK)
            except zmq.error.ZMQError as e:
                logging.debug("Sending TX Error: " + str(e))
                self.socket_ids.remove(id)

        while self.running:
            socks = dict(poller.poll(50))
            if self.tcpsocket in socks:
                id = self.tcpsocket.recv()
                message = self.tcpsocket.recv()
                if id not in self.socket_ids:
                    logging.debug("Added Socket ID: " + id.hex())
                    self.socket_ids.append(id)
                logging.debug("TCP ID: %s, RX: %s", id.hex(), message.decode('utf-8').rstrip())
                if message:
                    logging.debug("ZMQ PUB TX: %s", message.decode('utf-8').rstrip())
                    self.tx_zmq_pub.send(message)
                else:
                    if id in self.socket_ids:
                        logging.debug("Removed Socket ID: " + id.hex())
                        self.socket_ids.remove(id)
            if self.rx_zmq_sub in socks:
                data = self.rx_zmq_sub.recv()
                for id in self.socket_ids:
                    logging.debug("TCP ID: %s, Tx: %s", id.hex(), data.decode('utf-8').rstrip())
                    __zmq_tcp_send(id, data)
            if rx_zconf_pull in socks:
                name, action, ip_address, sub_port, pub_port = rx_zconf_pull.recv_multipart()
                if action == b'add':
                    logging.debug("Added device: %s", name.decode('utf-8'))
                    self.connect_zmq_device(name, ip_address, sub_port, pub_port)
                elif action == b'remove':
                    logging.debug("Remove device: %s", name.decode('utf-8'))
                    try:
                        self.disconnect_zmq_device(name, ip_address, sub_port, pub_port)
                    except zmq.error.ZMQError:
                        pass

        self.zeroconf.unregister_all_services()
        self.zeroconf.close()
        self.tcpsocket.close()
        self.tx_zmq_pub.close()
        self.rx_zmq_sub.close()
        self.rx_zconf_pull.close()


def init_logging(logfilename, level):
    log_level = logging.WARN
    if level == 1:
        log_level = logging.INFO
    elif level == 2:
        log_level = logging.DEBUG
    if not logfilename:
        formatter = logging.Formatter("%(asctime)s, %(message)s")
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.setLevel(log_level)
    else:
        logging.basicConfig(
            filename=logfilename,
            level=log_level,
            format="%(asctime)s, %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    logging.info("==== Started ====")


shutdown = False


def signal_cntrl_c(os_signal, os_frame):
    global shutdown
    shutdown = True


def main():
    # Catch CNTRL-C signel
    global shutdown
    signal.signal(signal.SIGINT, signal_cntrl_c)

    init_logging("", 2)
    context = zmq.Context.instance()
    zeroconf = Zeroconf()
    listener = ZeroConfListener(context)
    browser = ServiceBrowser(zeroconf, "_DashZMQ._tcp.local.", listener)

    b = zmq_tcpBridge(tcp_port=5001, context=context)

    while not shutdown:
        time.sleep(1)

    print("Goodbye")
    zeroconf.unregister_all_services()
    b.close()
    time.sleep(1)
    zeroconf.close()


if __name__ == "__main__":
    main()
