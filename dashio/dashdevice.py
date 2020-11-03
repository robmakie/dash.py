import logging
import zmq
import threading
import socket

from .iotcontrol.name import Name
from .iotcontrol.alarm import Alarm
from .iotcontrol.page import Page

from zeroconf import IPVersion, ServiceInfo, Zeroconf


class dashDevice(threading.Thread):

    """Setups and manages a connection thread to iotdashboard via TCP."""

    def __on_message(self, payload):
        data = str(payload, "utf-8").strip()
        command_array = data.split("\n")
        reply = ""
        for ca in command_array:
            try:
                reply += self.__on_command(ca.strip())
            except TypeError:
                pass
        return reply

    def __on_command(self, data):
        data_array = data.split("\t")
        rx_device_id = data_array[0]
        reply = ""
        if rx_device_id == "WHO":
            reply = self.device_id_str + "\tWHO\t{}\t{}\n".format(self.device_type, self.device_name_cntrl.control_id)
            return reply
        elif rx_device_id != self.device_id:
            return reply
        cntrl_type = data_array[1]
        if cntrl_type == "CONNECT":
            reply = self.connect
        elif cntrl_type == "STATUS":
            reply = self.__make_status()
        elif cntrl_type == "CFG":
            reply = self.__make_cfg()
        elif cntrl_type == "NAME":
            self.device_name_cntrl.message_rx_event(data_array[2:])
        else:
            try:
                key = cntrl_type + "_" + data_array[2]
            except IndexError:
                return
            try:
                self.control_dict[key].message_rx_event(data_array[3:])
            except KeyError:
                pass
        return reply

    def __make_status(self):
        reply = ""
        for key in self.control_dict.keys():
            try:
                status = self.control_dict[key].get_state()
                if status:
                    reply += self.device_id_str + self.__insert_device_id(self.control_dict[key].get_state())
            except TypeError:
                pass
        return reply

    def __make_cfg(self):
        reply = ""
        if self.number_of_pages:
            reply = self.device_id_str + '\tCFG\tDVCE\t{{"numPages": {}}}\n'.format(self.number_of_pages)
        for key in self.control_dict.keys():
            reply += self.device_id_str + self.control_dict[key].get_cfg()
        for key in self.alarm_dict.keys():
            reply += self.alarm_dict[key].get_cfg()
        return reply

    def send_popup_message(self, title, header, message):
        """Send a popup message to the Dash server.

        Parameters
        ----------
        title : str
            Title of the message.
        header : str
            Header of the message.
        message : str
            Message body.
        """
        data = self.device_id_str + "\tMSSG\t{}\t{}\t{}\n".format(title, header, message)
        self.tx_zmq_pub.send_multipart([b"ALL", b'0', data.encode('utf-8')])

    def send_alarm(self, alarm_id, message_header, message_body):
        """Send an Alarm to the Dash server.

        Parameters
        ----------
        alarm_id : str
            An identifier used by iotdashboard to manage the alarm. It should be unique for each connection.
        message_header : str
            Title for the Alarm.
        message_body : str
            The text body of the Alarm.
        """

        payload = self.device_id_str + "\t{}\t{}\t{}\n".format(alarm_id, message_header, message_body)
        logging.debug("ALARM: %s", payload)
        self.tx_zmq_pub.send_multipart([b"ALARM", b'0', payload.encode('utf-8')])

    def __send_dash_connect(self):
        data = self.device_id_str + "\tWHO\t{}\t{}\n".format(self.device_type, self.device_name_cntrl.control_id)
        self.tx_zmq_pub.send_multipart([b'ANNOUNCE', b'0', data.encode('utf-8')])

    def __insert_device_id(self, data):
        msg = data.rstrip()
        reply = msg.replace("\n", "\n\t{}".format(self.device_id))
        return reply + "\n"

    def send_data(self, data):
        """Send data.

        Parameters
        ----------
        data : str
            Data to be sent
        """
        msg = self.device_id_str + self.__insert_device_id(data)
        self.tx_zmq_pub.send_multipart([b"ALL", b'0', msg.encode('utf-8')])

    def add_control(self, iot_control):
        """Add a control to the connection.

        Parameters
        ----------
        iot_control : iotControl
        """
        if isinstance(iot_control, Alarm):
            iot_control.message_tx_event += self.send_alarm
            key = iot_control.msg_type + "_" + iot_control.control_id
            self.alarm_dict[key] = iot_control
        else:
            if isinstance(iot_control, Page):
                self.number_of_pages += 1
            iot_control.message_tx_event += self.send_data
            key = iot_control.msg_type + "_" + iot_control.control_id
            self.control_dict[key] = iot_control

    def add_connection(self, connection_id):
        tx_url_internal = "inproc://RX_{}".format(connection_id.hex)
        rx_url_internal = "inproc://TX_{}".format(connection_id.hex)
        self.tx_zmq_pub.connect(tx_url_internal)
        self.rx_zmq_sub.connect(rx_url_internal)

    def __init__(self, device_type, device_id, device_name, context=None) -> None:
        threading.Thread.__init__(self, daemon=True)

        self.context = context or zmq.Context.instance()

        self.tx_zmq_pub = self.context.socket(zmq.PUB)
        self.rx_zmq_sub = self.context.socket(zmq.SUB)

        self.rx_zmq_sub.setsockopt(zmq.SUBSCRIBE, b"")
        self.poller = zmq.Poller()
        self.poller.register(self.rx_zmq_sub, zmq.POLLIN)

        self.device_type = device_type
        self.device_id = device_id
        self.device_name_cntrl = Name(device_name)
        self.num_mqtt_connections = 0
        self.num_dash_connections = 0
        self.num_zmq_connections = 0
        self.zero_service_list = []
        self.connections = {}
        self.control_dict = {}
        self.alarm_dict = {}

        self.add_control(self.device_name_cntrl)
        self.device_id_str = "\t{}".format(device_id)
        self.connect = self.device_id_str + "\tCONNECT\n"
        self.number_of_pages = 0
        self.running = True
        self.local_ip = self.__get_local_ip_address()
        self.host_name = socket.gethostname()
        hs = self.host_name.split(".")
        # rename for .local mDNS advertising
        self.host_name = "{}.local".format(hs[0])

        logging.debug("HostName: %s", self.host_name)
        logging.debug("      IP: %s", self.local_ip)

        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self.start()

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
        zconf_desc = {'deviceID': self.device_id,
                      'deviceType': self.device_type,
                      'deviceName': self.device_name_cntrl.control_id}
        zconf_info = ServiceInfo(
            "_DashIO._tcp.local.",
            "{} {}._DashIO._tcp.local.".format(self.device_type, self.device_id),
            addresses=[socket.inet_aton(self.local_ip)],
            port=port,
            properties=zconf_desc,
            server=self.host_name + ".",
        )
        self.zeroconf.register_service(zconf_info)
        self.zero_service_list.append(zconf_info)

    def __zconf_publish_zmq(self, sub_port, pub_port):
        zconf_desc = {'deviceID': self.device_id,
                      'deviceType': self.device_type,
                      'deviceName': self.device_name_cntrl.control_id,
                      'sub_port': str(sub_port),
                      'pub_port': str(pub_port)}
        zconf_info = ServiceInfo(
            "_DashZMQ._tcp.local.",
            "{} {}._DashZMQ._tcp.local.".format(self.device_type, self.device_id),
            addresses=[socket.inet_aton(self.local_ip)],
            port=pub_port,
            properties=zconf_desc,
            server=self.host_name + ".",
        )
        self.zeroconf.register_service(zconf_info)
        self.zero_service_list.append(zconf_info)

    def close(self):
        self.running = False
        for conn in self.connections:
            self.connections[conn].running = False
        self.zeroconf.unregister_all_services()
        self.zeroconf.close()

    def run(self):
        # Continue the network loop, exit when an error occurs
        print("Hello")
        while self.running:
            socks = dict(self.poller.poll())
            if self.rx_zmq_sub in socks:
                msg = self.rx_zmq_sub.recv_multipart()
                if len(msg) == 3:
                    reply = self.__on_message(msg[2])
                    if reply:
                        self.tx_zmq_pub.send_multipart([msg[0], msg[1], reply.encode('utf-8')])

        self.tx_zmq_pub.close()
        self.rx_zmq_sub.close()

        for conn in self.connections:
            self.connections[conn].running = False
        self.context.term()
