
from .iotcontrol.name import Name
from .iotcontrol.alarm import Alarm
from .iotcontrol.page import Page

from .mqttconnection import mqttConnectionThread
from .tcpconnection import tcpConnectionThread

class dashDevice():

    """Setups and manages a connection thread to iotdashboard via TCP."""

    def __on_message(self, data):
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
        cntrl_type = data_array[0]
        reply = ""
        if cntrl_type == "CONNECT":
            reply = "\tCONNECT\t{}\t{}\t{}\n".format(self.name_cntrl.control_id, self.device_id, self.connection_id)
        elif cntrl_type == "WHO":
            reply = self.who
        elif cntrl_type == "STATUS":
            reply = self.__make_status()
        elif cntrl_type == "CFG":
            reply = self.__make_cfg()
        elif cntrl_type == "NAME":
            self.name_cntrl.message_rx_event(data_array[1:])
        else:
            try:
                key = cntrl_type + "_" + data_array[1]
            except IndexError:
                return
            try:
                self.control_dict[key].message_rx_event(data_array[2:])
            except KeyError:
                pass
        return reply

    def __make_status(self):
        reply = ""
        for key in self.control_dict.keys():
            try:
                reply += self.control_dict[key].get_state()
            except TypeError:
                pass
        return reply

    def __make_cfg(self):
        reply = '\tCFG\tDVCE\t{{"numPages": {}}}\n'.format(self.number_of_pages)
        for key in self.control_dict.keys():
            reply += self.control_dict[key].get_cfg()
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
        data = "\tMSSG\t{}\t{}\t{}\n".format(title, header, message)
        self.send_data(data)

    def send_data(self, data):
        """Send data to the Dash server.

        Parameters
        ----------
        data : str
            Data to be sent to the server
        """
        self.frontend.send_string(data)

    def add_control(self, iot_control):
        """Add a control to the connection.

        Parameters
        ----------
        iot_control : iotControl
        """
        if isinstance(iot_control, Alarm):
            pass
        else:
            if isinstance(iot_control, Page):
                self.number_of_pages += 1
            iot_control.message_tx_event += self.send_data
            key = iot_control.msg_type + "_" + iot_control.control_id
            self.control_dict[key] = iot_control




    def __init__(self, device_type, device_id, device_name) -> None:
        self.device_type = device_type
        self.device_id = device_id
        self.name_control = Name(device_name)
        self.num_mqtt_connections = 0
        self.connections = {}

    def add_mqtt_connection(self, host, port, username, password, use_ssl=False):
        self.num_mqtt_connections += 1
        connection_id = self.device_type + "_MQTT" + str(self.num_mqtt_connections)
        new_mqtt_con = mqttConnectionThread(connection_id, self.device_id, self.name_control, host, port, username, password, use_ssl)
        new_mqtt_con.start()
        new_mqtt_con.add_control(self.name_control)
        self.connections[connection_id] = new_mqtt_con

    def add_tcp_connection(self, url, port):
        connection_id = self.device_type + "_TCP:{}".format(str(port))
        new_tcp_con = tcpConnectionThread(connection_id ,self.device_id, self.name_control, url, port)
        new_tcp_con.start()
        new_tcp_con.add_control(self.name_control)
        self.connections[connection_id] = new_tcp_con

    def add_control(self, control):
        for conn in self.connections:
            self.connections[conn].add_control(control)

    def send_popup_message(self, title, header, message):
        for conn in self.connections:
            self.connections[conn].send_popup_message(title, header, message)

    def close(self):
        for conn in self.connections:
            self.connections[conn].running = False
