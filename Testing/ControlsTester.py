#!/bin/python3

import time
import random
import argparse
import signal
import dashio
import logging
import numpy as np


from dashio.iotcontrol.enums import ButtonState, Icon, LabelStyle
from dashio.iotcontrol.graph import GraphLine


class TestControls:
    def signal_cntrl_c(self, os_signal, os_frame):
        self.shutdown = True

    def init_logging(self, logfilename, level):
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

    def parse_commandline_arguments(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-v",
            "--verbose",
            const=1,
            default=1,
            type=int,
            nargs="?",
            help="""increase verbosity:
                            0 = only warnings, 1 = info, 2 = debug.
                            No number means info. Default is no verbosity.""",
        )
        parser.add_argument("-s", "--server", help="Server URL.", dest="server", default="dash.dashio.io")
        parser.add_argument("-q", "--hostname", help="Host URL.", dest="hostname", default="tcp://*")
        parser.add_argument(
            "-t", "--device_type", dest="device_type", default="Test_Controls", help="IotDashboard device type"
        )
        parser.add_argument(
            "-p", "--port", type=int, help="TCP Port number.", default=5000, dest="port",
        )
        parser.add_argument("-d", "--device_id", dest="device_id", default="00001", help="IotDashboard Device ID.")
        parser.add_argument(
            "-n", "--device_name", dest="device_name", default="Test_Controls", help="Alias name for device."
        )
        parser.add_argument("-u", "--user_name", help="MQTT Username", dest="username", default="")
        parser.add_argument("-w", "--password", help="MQTT Password", default="")
        parser.add_argument("-l", "--logfile", dest="logfilename", default="", help="logfile location", metavar="FILE")
        args = parser.parse_args()
        return args

    def up_btn_event_handler(self, msg):
        if self.btn1.btn_state == ButtonState.ON:
            self.btn1.btn_state = ButtonState.OFF
        else:
            self.btn1.btn_state = ButtonState.ON

    def down_btn_event_handler(self, msg):
        if self.btn2.btn_state == ButtonState.ON:
            self.btn2.btn_state = ButtonState.OFF
        else:
            self.btn2.btn_state = ButtonState.ON

    def slider_event_handler(self, msg):
        self.sldr_cntrl.slider_value = float(msg[0])
        self.knb_control.knob_dial_value = float(msg[0])

    def slider_dbl_event_handler(self, msg):
        self.sldr_dbl_cntrl.slider_value = float(msg[0])
        self.selector_ctrl.position = int(float(msg[0]))

    def knb_normal_event_handler(self, msg):
        self.knb_pan.knob_dial_value = float(msg[0])

    def knb_pan_event_handler(self, msg):
        self.knb_normal.knob_dial_value = float(msg[0])

    def text_cntrl_message_handler(self, msg):
        self.device.send_popup_message("TCPTest", "Text Box message", msg[0])
        self.text_cntrl.text = "Popup sent: " + msg[0]
        logging.info(msg)

    def selector_ctrl_handler(self, msg):
        print(self.selector_ctrl.selection_list[int(msg[0])])

    def _init_knobs(self):
        self.page_knobs = dashio.Page("Testknobs", "Knobs")
        self.knb_normal = dashio.Knob("KNB_NORMAL",
                                      knob_style=dashio.KnobStyle.NORMAL,
                                      control_position=dashio.ControlPosition(0.24, 0.14, 0.54, 0.26))
        self.knb_normal.message_rx_event += self.knb_normal_event_handler
        self.knb_normal.title = "Knob Normal"
        self.knb_normal.max = 10
        self.knb_normal.red_value = 8
        self.page_knobs.add_control(self.knb_normal)

        self.knb_pan = dashio.Knob("KNB_PAN",
                                   knob_style=dashio.KnobStyle.PAN,
                                   control_position=dashio.ControlPosition(0.24, 0.44, 0.54, 0.26))

        self.knb_pan.message_rx_event += self.knb_pan_event_handler
        self.knb_pan.title = "Knob Pan"
        self.knb_pan.max = 10
        self.knb_pan.red_value = 8
        self.page_knobs.add_control(self.knb_pan)
        self.device.add_control(self.page_knobs)
        self.device.add_control(self.knb_normal)
        self.device.add_control(self.knb_pan)

    def _init_buttons(self):
        self.page_btns = dashio.Page("TestButtons", "Buttons")
        self.btn1 = dashio.Button("BTN1",
                                  "Up",
                                  icon_name=Icon.UP,
                                  control_position=dashio.ControlPosition(0.24, 0.14, 0.54, 0.26))
        self.btn1.btn_state = ButtonState.ON
        self.btn1.message_rx_event += self.up_btn_event_handler
        self.btn2 = dashio.Button("BTN2",
                                  "Down",
                                  icon_name=Icon.DOWN,
                                  control_position=dashio.ControlPosition(0.24, 0.44, 0.54, 0.26))
        self.btn2.btn_state = ButtonState.ON
        self.btn2.message_rx_event += self.down_btn_event_handler
        self.page_btns.add_control(self.btn1)
        self.page_btns.add_control(self.btn2)
        self.device.add_control(self.page_btns)
        self.device.add_control(self.btn1)
        self.device.add_control(self.btn2)

    def _init_dials(self):
        self.page_dials = dashio.Page("TestDials", "Dials")
        self.compass = dashio.Compass("TestCompass",
                                      "Direction",
                                      control_position=dashio.ControlPosition(0.24, 0.1, 0.54, 0.25))
        self.dial_std = dashio.Dial("DialSTD", "Dial Standard",
                                    style=dashio.DialStyle.STD,
                                    control_position=dashio.ControlPosition(0.24, 0.36, 0.54, 0.26))
        self.dial_inv = dashio.Dial("Dial",
                                    "Dial Inverted",
                                    style=dashio.DialStyle.INVERTED,
                                    control_position=dashio.ControlPosition(0.24, 0.61, 0.54, 0.26))
        self.page_dials.add_control(self.compass)
        self.page_dials.add_control(self.dial_std)
        self.page_dials.add_control(self.dial_inv)
        self.device.add_control(self.page_dials)
        self.device.add_control(self.compass)
        self.device.add_control(self.dial_std)
        self.device.add_control(self.dial_inv)

    def _init_event_log(self):
        self.page_el = dashio.Page("EventLog", "Event Log")
        self.event_log = dashio.EventLog("eventlog",
                                         "Event Log",
                                         control_position=dashio.ControlPosition(0.0, 0.1, 1.0, 0.2))
        self.page_el.add_control(self.event_log)
        self.device.add_control(self.page_el)
        self.device.add_control(self.event_log)

    def _init_graph(self):
        data = np.random.normal(0, 20, 100)
        bins = np.arange(-100, 100, 5)
        hist, hist_edges = np.histogram(data, bins)
        p_data = []
        s_data = []
        for x in range(-50, 50, 1):
            y = 0.03 * x ** 2 + 2
            p_data.append(y)
            s_data.append(100 - y)
        self.page_graph = dashio.Page("graph_pg", "Graph")
        self.graph = dashio.Graph("graph1",
                                  "Graph",
                                  control_position=dashio.ControlPosition(0.0, 0.0, 1.0, 1.0))
        self.graph.x_axis_label = "X Axis"
        self.graph.y_axis_label = "Y Axis"
        self.graph.x_axis_min = min(data) - 5
        self.graph.x_axis_max = max(data) + 5
        self.graph.x_axis_labels_style = dashio.GraphXAxisLabelsStyle.ON
        self.page_graph.add_control(self.graph)
        self.device.add_control(self.page_graph)
        self.device.add_control(self.graph)
        self.gl_line = GraphLine("graph_line", dashio.GraphLineType.LINE, color=dashio.Color.BLUE)
        data += 50
        self.gl_line.data = data.tolist()
        self.graph.add_line("graph_line", self.gl_line)
        self.gl_bar = GraphLine("graph_bar", dashio.GraphLineType.BAR, color=dashio.Color.GREEN)
        self.gl_bar.data = hist.tolist()
        self.graph.add_line("graph_bar", self.gl_bar)
        self.gl_segbar = GraphLine("graph_seg_bar", dashio.GraphLineType.SEGBAR, color=dashio.Color.YELLOW)
        self.gl_segbar.data = p_data
        self.graph.add_line("graph_segbar", self.gl_segbar)
        self.gl_peakbar = GraphLine("graph_peakbar", dashio.GraphLineType.PEAKBAR, color=dashio.Color.RED)
        self.gl_peakbar.data = s_data
        self.graph.add_line("graph_parkbar", self.gl_peakbar)

    def _init_labels(self):
        self.page_label = dashio.Page("label_pg", "Labels")
        self.device.add_control(self.page_label)
        self.label_basic = dashio.Label("label_basic",
                                        "Basic",
                                        style=LabelStyle.BASIC,
                                        control_position=dashio.ControlPosition(0.18, 0.05, 0.7, 0.22))
        self.page_label.add_control(self.label_basic)
        self.device.add_control(self.label_basic)

        self.label_border = dashio.Label("label_border",
                                         "Border",
                                         style=LabelStyle.BORDER,
                                         control_position=dashio.ControlPosition(0.18, 0.31, 0.7, 0.3))
        self.page_label.add_control(self.label_border)
        self.device.add_control(self.label_border)

        self.label_group = dashio.Label("label_group",
                                        "Group",
                                        style=LabelStyle.GROUP,
                                        control_position=dashio.ControlPosition(0.18, 0.65, 0.7, 0.3))
        self.page_label.add_control(self.label_group)
        self.device.add_control(self.label_group)

    def _init_map(self):
        self.page_map = dashio.Page("map_pg", "Map")
        self.device.add_control(self.page_map)
        self.map = dashio.Map("map",
                              "Map",
                              control_position=dashio.ControlPosition(0.0, 0.0, 1.0, 1.0))
        self.map_loc1 = dashio.SimpleMapLocation("Mt. Cook", -43.59412841615468, 170.14189062192213)
        self.map_loc2 = dashio.MapLocation("James Peak", -45.237101516008835, 168.84818243505748)
        self.map.add_location(self.map_loc1)
        self.map.add_location(self.map_loc2)
        self.page_map.add_control(self.map)
        self.device.add_control(self.map)

    def left_btn_event_handler(self, msg):
        temp_value = self.menu_sldr.slider_value
        if temp_value > 0:
            self.menu_sldr.slider_value = temp_value - 1

    def right_btn_event_handler(self, msg):
        temp_value = self.menu_sldr.slider_value
        if temp_value < 20:
            self.menu_sldr.slider_value = temp_value + 1

    def _init_menu(self):
        self.page_menu = dashio.Page("menu_pg", "Menus")
        self.device.add_control(self.page_menu)
        self.menu = dashio.Menu("menu", "Menu", control_position=dashio.ControlPosition(0.18, 0.2, 0.7, 0.22))
        self.btn_group = dashio.ButtonGroup("btn_group",
                                            "Button",
                                            control_position=dashio.ControlPosition(0.18, 0.5, 0.7, 0.22))
        self.device.add_control(self.menu)
        self.device.add_control(self.btn_group)
        self.page_menu.add_control(self.menu)
        self.page_menu.add_control(self.btn_group)
        self.btn3 = dashio.Button("btn3", "Menu Button1", icon_name=Icon.LEFT)
        self.btn3.message_rx_event += self.left_btn_event_handler
        self.btn4 = dashio.Button("btn4", "Menu Button2", icon_name=Icon.RIGHT)
        self.btn4.message_rx_event += self.right_btn_event_handler

        self.btn5 = dashio.Button("btn5", "Group Button1", icon_name=Icon.LEFT)
        self.btn5.message_rx_event += self.left_btn_event_handler
        self.btn6 = dashio.Button("btn6", "Group Button2", icon_name=Icon.RIGHT)
        self.btn6.message_rx_event += self.right_btn_event_handler

        self.menu_tb = dashio.TextBox("txt1", "Menu TextBox")
        self.menu_sldr = dashio.SliderSingleBar("mnu_sldr", "Menu Slider")
        self.menu_sldr.max = 20
        self.menu_sldr.min = 0
        self.menu_slctr = dashio.Selector("sltr1", "Menu Selector")
        self.menu.add_control(self.btn3)
        self.menu.add_control(self.btn4)
        self.btn_group.add_button(self.btn5)
        self.btn_group.add_button(self.btn6)
        self.menu.add_control(self.menu_tb)
        self.menu.add_control(self.menu_sldr)
        self.menu.add_control(self.menu_slctr)
        self.device.add_control(self.btn3)
        self.device.add_control(self.btn4)
        self.device.add_control(self.btn5)
        self.device.add_control(self.btn6)
        self.device.add_control(self.menu_tb)
        self.device.add_control(self.menu_sldr)
        self.device.add_control(self.menu_slctr)

    
    def slider_1_event_handler(self, msg):
        self.sldr_dble_solid.bar1_value = float(msg[0])
        self.sldr_dble_segmnt.bar1_value = float(msg[0])

    def slider_2_event_handler(self, msg):
        self.sldr_dble_solid.bar2_value = float(msg[0])
        self.sldr_dble_segmnt.bar2_value = float(msg[0])
    
    def slider_3_event_handler(self, msg):
        self.sldr_single_solid.bar1_value = float(msg[0])

    def slider_4_event_handler(self, msg):
        self.sldr_single_segmnt.bar1_value = float(msg[0])

    def _init_selector(self):
        self.page_sel_slid = dashio.Page("slctr_pg", "Selector & Sliders")
        self.device.add_control(self.page_sel_slid)
        self.slctr1 = dashio.Selector("slctr1",
                                      "Selector",
                                      control_position=dashio.ControlPosition(0.0, 0.8, 1.0, 0.2))
        self.device.add_control(self.slctr1)
        self.slctr1.add_selection("Selection 1")
        self.slctr1.add_selection("Selection 2")
        self.slctr1.add_selection("Selection 3")
        self.slctr1.add_selection("Selection 4")
        self.slctr1.add_selection("Selection 5")
        self.slctr1.add_selection("Selection 6")
        self.sldr_single_solid = dashio.SliderSingleBar("sldr_single_solid",
                                                        "Single Slider Solid",
                                                        bar_style=dashio.SliderBarType.SOLID,
                                                        control_position=dashio.ControlPosition(0.0, 0.0, 0.25, 0.8))
        self.sldr_single_solid.message_rx_event += self.slider_1_event_handler
        self.sldr_single_segmnt = dashio.SliderSingleBar("sldr_single_segment",
                                                         "Single Slider Segmented",
                                                         bar_style=dashio.SliderBarType.SEGMENTED,
                                                         control_position=dashio.ControlPosition(0.25, 0.0, 0.25, 0.8))
        self.sldr_single_segmnt.message_rx_event += self.slider_2_event_handler
        
        self.sldr_dble_solid = dashio.SliderDoubleBar("sldr_double_solid",
                                                        "Double Slider Solid",
                                                        bar_style=dashio.SliderBarType.SOLID,
                                                        control_position=dashio.ControlPosition(0.5, 0.0, 0.25, 0.8))
        self.sldr_dble_solid.message_rx_event += self.slider_3_event_handler
        self.sldr_dble_segmnt = dashio.SliderDoubleBar("sldr_double_segment",
                                                         "Double Slider Segmented",
                                                         bar_style=dashio.SliderBarType.SEGMENTED,
                                                         control_position=dashio.ControlPosition(0.75, 0.0, 0.25, 0.8))
        self.sldr_dble_segmnt.message_rx_event += self.slider_4_event_handler
        self.page_sel_slid.add_control(self.slctr1)
        self.page_sel_slid.add_control(self.sldr_single_solid)
        self.page_sel_slid.add_control(self.sldr_single_segmnt)
        self.page_sel_slid.add_control(self.sldr_dble_solid)
        self.page_sel_slid.add_control(self.sldr_dble_segmnt)


        self.device.add_control(self.sldr_single_solid)
        self.device.add_control(self.sldr_single_segmnt)
        self.device.add_control(self.sldr_dble_solid)
        self.device.add_control(self.sldr_dble_segmnt)

    def _init_text_box(self):
        self.text_box_menu = dashio.Page("tb_pg", "Text Box")
        self.device.add_control(self.text_box_menu)

    def _init_time_graph(self):
        self.time_graph_menu = dashio.Page("time_graph_pg", "Time Graph")
        self.device.add_control(self.time_graph_menu)

    def __init__(self):

        # Catch CNTRL-C signel
        signal.signal(signal.SIGINT, self.signal_cntrl_c)
        self.shutdown = False
        args = self.parse_commandline_arguments()
        self.init_logging(args.logfilename, args.verbose)

        logging.info("   Serving on: %s", args.server)
        logging.info("  Device Type: %s", args.device_type)
        logging.info("    Device ID: %s", args.device_id)
        logging.info("  Device Name: %s", args.device_name)

        self.device = dashio.dashDevice(args.device_type, args.device_id, args.device_name)
        #self.tcp_con = dashio.tcpConnection(port=args.port)
        self.dash_con = dashio.dashConnection(args.username, args.password)
        #self.tcp_con.add_device(self.device)
        self.dash_con.add_device(self.device)
        self._init_knobs()
        self._init_buttons()
        self._init_dials()
        self._init_event_log()
        self._init_graph()
        self._init_labels()
        self._init_map()
        self._init_menu()
        self._init_selector()
        self._init_text_box()
        self._init_time_graph()
        while not self.shutdown:
            time.sleep(5)
            self.compass.direction_value = random.random() * 360
            ed = dashio.EventData("Compass Direction", "{:.2f}".format(self.compass.direction_value))
            self.event_log.add_event_data(ed)
            if len(self.event_log.log_list) > 15:
                self.event_log.log_list.pop(0)
            self.dial_std.dial_value = random.random() * 100
            self.dial_inv.dial_value = random.random() * 100

        self.device.send_popup_message("TestControls", "Shutting down", "Goodbye")
        self.device.close()


def main():
    tc = TestControls()


if __name__ == "__main__":
    main()
