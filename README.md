# Dash.py

A python library to connect to the Iot Dashboard.

## Getting Started

$ cd Examples
$ python3 iot_monitor.py -s dash.io -p 8883 -u user -w password -c`hostname`

Will create a graph of network traffic with a connection_id of your hostname. The control and data topics are hostname_data and hostname_control.

## Requirements

* python3

## Install

pip3 install dashio
